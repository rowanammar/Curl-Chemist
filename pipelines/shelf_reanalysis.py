"""
Shelf Reanalysis Pipeline — Autonomous Agent Version.

BEFORE: A rigid 6-step Python script that called functions in a fixed order.
AFTER:  A single goal handed to the TaskmasterOrchestrator. The LLM
        autonomously decides which tools to call and in what order.

Triggered when a product photo is uploaded to Cloud Storage (via Pub/Sub)
or manually from the dashboard.
"""

from pipelines.orchestrator import run_agent_loop
from pipelines.tool_registry import SHELF_REANALYSIS_TOOLS
from firestore_helpers import log_pipeline_event, get_user_location, clear_all_conflicts


async def run_shelf_reanalysis_pipeline(user_id: str, image_uri: str, file_name: str):
    """
    Execute the shelf reanalysis cascade for a specific user.

    The TaskmasterOrchestrator receives a goal and autonomously:
    1. Scans the product label to extract ingredients
    2. Saves the product to the user's shelf
    3. Runs N×N conflict analysis against the entire shelf
    4. Saves any detected conflicts
    5. If critical conflicts involve a missing necessity (e.g., heavy silicones
       without a clarifying shampoo), dispatches a proactive shopping alert
    6. Reports a summary of findings

    Args:
        user_id: the user who uploaded the photo
        image_uri: Cloud Storage URI of the uploaded product photo
        file_name: Original filename for logging
    """
    pipeline_name = "shelf_reanalysis"

    log_pipeline_event(
        user_id, pipeline_name,
        f"Cascade triggered by upload: {file_name}"
    )

    location = get_user_location(user_id)
    user_city = location.get("city", "their city/country")

    goal = f"""You are the Shelf Reanalysis Agent for Curl Chemist. A new product photo was just uploaded.

IMAGE URI: {image_uri}
FILE NAME: {file_name}
USER ID: {user_id}
USER LOCATION: {user_city}

YOUR MISSION (execute these steps using the tools available to you):
1. Use scan_label to extract the product's ingredients from the photo at the given image_uri.
2. Use save_product_to_shelf to save the extracted product data to the user's shelf. Pass user_id="{user_id}" and the product data as a JSON string.
3. Use get_shelf to retrieve ALL products currently on the user's shelf (user_id="{user_id}").
4. Use analyze_conflicts to run N×N conflict analysis across the entire shelf (user_id="{user_id}").
5. For EACH conflict found, use save_conflict_to_db to persist it (user_id="{user_id}").
6. CRITICAL CHECK: Review the conflicts. ONLY use dispatch_shopping_alert for conflicts with a severity of EXACTLY "critical". Do NOT send shopping alerts for conflicts with "warning" or "info" severity. If a "critical" conflict exists (e.g., heavy silicones without a clarifying shampoo, or protein overload without moisture), send a shopping alert.
   IMPORTANT: When dispatching a shopping alert, you MUST use your knowledge to provide 3 specific product recommendations for the missing product: a Low Cost choice, a Premium choice, and a Local choice.
   RULES FOR RECOMMENDATIONS:
   - "Local Choice": MUST be a real, existent product from a brand local to or easily available in {user_city}. DO NOT hallucinate products.
   - "Low Cost Choice": MUST be a cheap product widely available in {user_city}.
   - "Premium Choice": MUST be a high-end product.
7. Provide a final summary of what product was added, how many conflicts were found, and any alerts dispatched.

IMPORTANT: Always pass user_id as the string "{user_id}" when calling tools that require it."""

    clear_all_conflicts(user_id)
    result = await run_agent_loop(goal, SHELF_REANALYSIS_TOOLS, user_id, pipeline_name)

    log_pipeline_event(
        user_id, pipeline_name,
        f"Shelf reanalysis cascade complete: {result.get('summary', 'done')[:200]}",
        status="success",
    )
    return result

async def run_shelf_check_pipeline(user_id: str):
    """
    Execute a targeted shelf check for a specific user after manual product addition.

    The TaskmasterOrchestrator receives a goal and autonomously:
    1. Retrieves ALL products currently on the user's shelf
    2. Runs N×N conflict analysis
    3. Saves any detected conflicts
    4. Dispatches a proactive shopping alert if critical conflicts exist

    Args:
        user_id: the user whose shelf was updated
    """
    pipeline_name = "shelf_check"

    log_pipeline_event(
        user_id, pipeline_name,
        f"Shelf check triggered by manual addition"
    )

    location = get_user_location(user_id)
    user_city = location.get("city", "their city/country")

    goal = f"""You are the Shelf Reanalysis Agent for Curl Chemist. The user has just manually added a new product to their shelf.

USER ID: {user_id}
USER LOCATION: {user_city}

YOUR MISSION (execute these steps using the tools available to you):
1. Use get_shelf to retrieve ALL products currently on the user's shelf (user_id="{user_id}").
2. Use analyze_conflicts to run N×N conflict analysis across the entire shelf (user_id="{user_id}").
3. For EACH conflict found, use save_conflict_to_db to persist it (user_id="{user_id}").
4. CRITICAL CHECK: Review the conflicts. ONLY use dispatch_shopping_alert for conflicts with a severity of EXACTLY "critical". Do NOT send shopping alerts for conflicts with "warning" or "info" severity. If a "critical" conflict exists (e.g., heavy silicones without a clarifying shampoo, or protein overload without moisture), send a shopping alert.
   IMPORTANT: When dispatching a shopping alert, you MUST use your knowledge to provide 3 specific product recommendations for the missing product: a Low Cost choice, a Premium choice, and a Local choice.
   RULES FOR RECOMMENDATIONS:
   - "Local Choice": MUST be a real, existent product from a brand local to or easily available in {user_city}. DO NOT hallucinate products.
   - "Low Cost Choice": MUST be a cheap product widely available in {user_city}.
   - "Premium Choice": MUST be a high-end product.
5. Provide a final summary of how many conflicts were found and any alerts dispatched.

IMPORTANT: Always pass user_id as the string "{user_id}" when calling tools that require it."""

    clear_all_conflicts(user_id)
    result = await run_agent_loop(goal, SHELF_REANALYSIS_TOOLS, user_id, pipeline_name)

    log_pipeline_event(
        user_id, pipeline_name,
        f"Shelf check complete: {result.get('summary', 'done')[:200]}",
        status="success",
    )

    return result