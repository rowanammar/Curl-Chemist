from datetime import datetime, timezone
from pipelines.orchestrator import run_agent_loop
from pipelines.tool_registry import WEEKLY_HEALTH_TOOLS
from firestore_helpers import log_pipeline_event

async def run_weekly_health_pipeline(user_id: str):
    """Execute the weekly hair health analysis pipeline using ReAct agent architecture."""
    pipeline_name = "weekly_health"
    now = datetime.now(timezone.utc)
    week_str = now.strftime("%Y-W%W")

    goal = f"""
    Analyze the user's wash history for the past 7 days to generate weekly health insights.
    
    Steps:
    1. Fetch the user's recent wash history. If there are no entries, you are done.
    2. Analyze the wash trends to compute improvements or declines.
    3. Generate 3-5 specific, actionable insights based on the trends and the user's hair profile. Example insights:
       - "Curl definition improved on days when you used [product] but not [product]"
       - "Frizz was worst on high-humidity days when you used glycerin-based products"
    4. Suggest 1-2 routine adjustments.
    5. Update the user's adaptive profile with these new routine adjustments and the latest trends.
    6. Save the weekly health report for week '{week_str}' containing the insights, routine adjustments, best day, and worst day.
    
    Always pass user_id='{user_id}' when calling tools.
    """

    try:
        log_pipeline_event(user_id, pipeline_name, "Weekly health analysis agent started")
        result = await run_agent_loop(
            goal=goal,
            tools=WEEKLY_HEALTH_TOOLS,
            user_id=user_id,
            pipeline_name=pipeline_name,
        )
        return {"status": "success", "agent_result": result}
    except Exception as e:
        log_pipeline_event(user_id, pipeline_name, f"Pipeline failed: {str(e)}", status="error")
        raise