"""
TaskmasterOrchestrator — True ReAct Agent Loop.

WHY THIS FILE EXISTS:
This replaces the rigid, hard-coded pipeline scripts with a genuine
autonomous agent. The LLM receives a GOAL and a set of TOOLS, then
decides on its own which tools to call and in what order.

KEY ARCHITECTURAL FEATURES:
- Agentic Autonomy: LLM sequences tool calls, not Python scripts
- Architectural Discipline: Clean ReAct loop with message history
- Robust State: Self-healing try/except with error feedback
- Observability: All reasoning + tool calls logged
"""

import json
import inspect
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

from google import genai
from google.genai import types
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION, GEMINI_API_KEY
from firestore_helpers import log_pipeline_event, save_agent_trace
from pipelines.input_sanitizer import InputSanitizer

# ── Constants ──
MAX_ITERATIONS = 15           # Prevent infinite loops
MAX_CONSECUTIVE_ERRORS = 3    # Force the agent to try a different approach

# ── Gemini client ──
_client = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if GEMINI_API_KEY:
            _client = genai.Client(api_key=GEMINI_API_KEY)
        else:
            _client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)
    return _client


ORCHESTRATOR_SYSTEM_PROMPT = """You are the Curl Chemist TaskmasterOrchestrator — an autonomous hair care agent.

You receive a GOAL and a set of TOOLS. Your job is to accomplish the goal by calling tools in whatever order you determine is best.

RULES:
1. Think step-by-step. Before each tool call, explain your reasoning.
2. After calling a tool, analyze the result before deciding the next step.
3. If a tool fails, read the error message carefully and fix your arguments.
4. Do NOT fabricate data — only use information returned by tools.
5. When the goal is fully accomplished, provide a final summary of what you did and what you found.
6. If you detect a critical issue that requires user action (missing products, severe conflicts), use the appropriate external action tool (shopping alert, calendar event).

FORMAT: Think aloud, then call tools. When done, provide a JSON summary wrapped in ```json``` fences.
"""


def _build_tool_declarations(tools: list[Callable]) -> list[types.Tool]:
    """Convert Python functions into GenAI Tool declarations.
    
    Uses the function's signature and docstring to build the schema
    the LLM uses to understand when/how to call each tool.
    """
    function_declarations = []

    for func in tools:
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""

        # Parse docstring for description (first paragraph)
        doc_lines = doc.split("\n\n")
        description = doc_lines[0].strip() if doc_lines else func.__name__

        # Build parameter schema from type hints
        properties = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param_name == "user_id":
                continue # Hide from LLM since it is bound server-side

            param_type = param.annotation
            if param_type == inspect.Parameter.empty:
                param_type = str

            # Map Python types to JSON schema types
            if param_type in (int, float):
                schema_type = types.Type.NUMBER
            elif param_type == bool:
                schema_type = types.Type.BOOLEAN
            elif param_type in (list, dict):
                schema_type = types.Type.STRING  # We pass complex types as JSON strings
            else:
                schema_type = types.Type.STRING

            # Extract parameter description from docstring Args section
            param_desc = f"Parameter: {param_name}"
            if "Args:" in doc:
                args_section = doc.split("Args:")[1].split("Returns:")[0]
                for line in args_section.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith(f"{param_name}:"):
                        param_desc = stripped.split(":", 1)[1].strip()
                        break

            properties[param_name] = types.Schema(
                type=schema_type,
                description=param_desc,
            )

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        function_declarations.append(types.FunctionDeclaration(
            name=func.__name__,
            description=description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties=properties,
                required=required,
            ),
        ))

    return [types.Tool(function_declarations=function_declarations)]


async def _execute_tool(func: Callable, args: dict) -> Any:
    """Execute a tool function, handling both sync and async functions."""
    if inspect.iscoroutinefunction(func):
        return await func(**args)
    else:
        return func(**args)


def _serialize_result(result: Any) -> str:
    """Safely serialize a tool result to a JSON string for the LLM."""
    try:
        if isinstance(result, (dict, list)):
            return json.dumps(result, default=str, ensure_ascii=False)
        return str(result)
    except Exception:
        return str(result)


async def run_agent_loop(
    goal: str,
    tools: list[Callable],
    user_id: str,
    pipeline_name: str,
) -> dict:
    """
    Run the ReAct agent loop: give the LLM a goal + tools,
    let it autonomously decide tool calls until it completes the task.

    Args:
        goal: Natural language description of what the agent should accomplish
        tools: List of Python functions the agent can call
        user_id: User ID for scoping Firestore operations and logging
        pipeline_name: Name for logging (e.g., "shelf_reanalysis")

    Returns:
        dict with status, summary, and trace of the agent's execution
    """
    client = _get_client()
    
    import functools
    bound_tools = []
    for func in tools:
        sig = inspect.signature(func)
        if "user_id" in sig.parameters:
            bound_func = functools.partial(func, user_id=user_id)
            functools.update_wrapper(bound_func, func)
            bound_tools.append(bound_func)
        else:
            bound_tools.append(func)

    tool_declarations = _build_tool_declarations(bound_tools)
    tool_map = {func.__name__: func for func in bound_tools}

    goal = InputSanitizer.scan_for_pii(goal)

    # Initialize message history
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=goal)]),
    ]

    # Trace log for observability
    trace_log = []
    consecutive_errors = 0
    final_summary = ""

    log_pipeline_event(
        user_id, pipeline_name,
        f"[AGENT START] Goal: {goal[:200]}...",
        status="info",
    )
    trace_log.append({"type": "goal", "content": goal, "timestamp": datetime.now(timezone.utc).isoformat()})

    config = types.GenerateContentConfig(
        system_instruction=ORCHESTRATOR_SYSTEM_PROMPT,
        tools=tool_declarations,
        temperature=0.2,
    )

    for iteration in range(MAX_ITERATIONS):
        try:
            response = await client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=config,
            )
        except Exception as e:
            log_pipeline_event(
                user_id, pipeline_name,
                f"[AGENT ERROR] LLM call failed at iteration {iteration}: {e}",
                status="error",
            )
            trace_log.append({"type": "llm_error", "error": str(e), "iteration": iteration})
            break

        if not response.candidates or not response.candidates[0].content.parts:
            log_pipeline_event(
                user_id, pipeline_name,
                f"[AGENT DONE] Empty response at iteration {iteration} — agent finished.",
                status="info",
            )
            break

        parts = response.candidates[0].content.parts

        # Append the full model response to history
        contents.append(response.candidates[0].content)

        # Process each part: text (thoughts) or function_call
        function_calls = []
        for part in parts:
            if part.text:
                # This is the agent's REASONING — log it!
                thought = part.text.strip()
                if thought:
                    log_pipeline_event(
                        user_id, pipeline_name,
                        f"[AGENT THOUGHT] {thought[:500]}",
                        status="agent_thought",
                    )
                    trace_log.append({
                        "type": "thought",
                        "content": thought,
                        "iteration": iteration,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    final_summary = thought  # Keep the last thought as summary

            if part.function_call:
                function_calls.append(part)

        # If no function calls, the agent is done
        if not function_calls:
            log_pipeline_event(
                user_id, pipeline_name,
                f"[AGENT DONE] Completed after {iteration + 1} iterations.",
                status="success",
            )
            break

        # Execute each tool call with self-healing
        function_responses = []
        for fc_part in function_calls:
            fc = fc_part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}
            tool_args = InputSanitizer.sanitize_tool_args(tool_args)

            log_pipeline_event(
                user_id, pipeline_name,
                f"[TOOL CALL] {tool_name}({json.dumps(tool_args, default=str)[:300]})",
                status="info",
            )
            trace_log.append({
                "type": "tool_call",
                "tool": tool_name,
                "args": tool_args,
                "iteration": iteration,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            if tool_name not in tool_map:
                error_msg = f"Unknown tool '{tool_name}'. Available tools: {list(tool_map.keys())}"
                log_pipeline_event(
                    user_id, pipeline_name,
                    f"[TOOL ERROR] {error_msg}",
                    status="warning",
                )
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"error": error_msg},
                    )
                )
                trace_log.append({"type": "tool_error", "tool": tool_name, "error": error_msg})
                consecutive_errors += 1
                continue

            try:
                result = await _execute_tool(tool_map[tool_name], tool_args)
                result_str = _serialize_result(result)

                log_pipeline_event(
                    user_id, pipeline_name,
                    f"[TOOL OK] {tool_name} → {result_str[:300]}",
                    status="success",
                )
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result_str},
                    )
                )
                trace_log.append({
                    "type": "tool_result",
                    "tool": tool_name,
                    "result_preview": result_str[:500],
                    "iteration": iteration,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                consecutive_errors = 0  # Reset on success

            except Exception as e:
                # ── Self-healing: feed the error back to the LLM ──
                error_detail = f"{type(e).__name__}: {str(e)}"
                tb = traceback.format_exc()

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS - 1:
                    error_msg = (
                        f"Tool execution failed with error: {error_detail}. "
                        f"This tool has failed {consecutive_errors + 1} times consecutively. "
                        f"Consider using a different approach or skipping this step."
                    )
                else:
                    error_msg = (
                        f"Tool execution failed with error: {error_detail}. "
                        f"Please fix your arguments and try again."
                    )

                log_pipeline_event(
                    user_id, pipeline_name,
                    f"[TOOL ERROR] {tool_name}: {error_detail}",
                    status="warning",
                )
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"error": error_msg},
                    )
                )
                trace_log.append({
                    "type": "tool_error",
                    "tool": tool_name,
                    "error": error_detail,
                    "traceback": tb[:500],
                    "iteration": iteration,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                consecutive_errors += 1

        # Append tool results to conversation for the next LLM turn
        contents.append(types.Content(role="user", parts=function_responses))

    else:
        # Exhausted MAX_ITERATIONS
        log_pipeline_event(
            user_id, pipeline_name,
            f"[AGENT WARNING] Reached max iterations ({MAX_ITERATIONS}). Returning partial result.",
            status="warning",
        )

    # Save full trace for demo replay
    save_agent_trace(user_id, pipeline_name, trace_log)

    return {
        "status": "success",
        "pipeline": pipeline_name,
        "iterations": min(iteration + 1, MAX_ITERATIONS) if 'iteration' in dir() else 0,
        "summary": final_summary,
        "trace_length": len(trace_log),
    }
