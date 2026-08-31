"""
Nightly Routine Pipeline — Autonomous Agent Version.

BEFORE: A rigid 6-step Python script that fetched weather, loaded products,
        checked conflicts, generated routine, and saved — all hard-coded.
AFTER:  A single goal handed to the TaskmasterOrchestrator. The LLM
        autonomously decides which tools to call and in what order.

Triggered by Cloud Scheduler at 9 PM daily, or manually from the dashboard.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pipelines.orchestrator import run_agent_loop
from pipelines.tool_registry import NIGHTLY_ROUTINE_TOOLS
from firestore_helpers import log_pipeline_event, get_user_location


async def run_nightly_routine_pipeline(user_id: str):
    """
    Execute the nightly routine generation pipeline for a specific user.

    The TaskmasterOrchestrator receives a goal and autonomously:
    1. Fetches tomorrow's weather for the user's location
    2. Loads the user's product shelf
    3. Loads the user's hair profile
    4. Checks for climate-dependent conflicts
    5. Generates a personalized daily routine
    6. Saves the routine to Firestore
    7. If the routine includes a wash day or deep conditioning,
       schedules a calendar event to block out time

    Called by the /pipelines/nightly endpoint when Cloud Scheduler
    fires at 9 PM, or manually by the user.
    """
    pipeline_name = "nightly_routine"

    log_pipeline_event(user_id, pipeline_name, "Pipeline triggered")

    # Calculate tomorrow's date for the agent using user's timezone
    location = get_user_location(user_id)
    user_tz_str = location.get("timezone", "UTC")
    try:
        user_tz = ZoneInfo(user_tz_str)
    except Exception:
        user_tz = ZoneInfo("UTC")
        
    tomorrow = datetime.now(user_tz) + timedelta(days=1)
    date_str = tomorrow.strftime("%Y-%m-%d")

    goal = f"""You are the Nightly Routine Agent for Curl Chemist. Generate tomorrow's personalized hair care routine.

USER ID: {user_id}
TARGET DATE: {date_str}

YOUR MISSION (execute these steps using the tools available to you):
1. Use fetch_weather_forecast to get tomorrow's weather for the user's location.
2. Use get_shelf to verify the user has products on their shelf.
   - If the shelf is empty, stop and report that no routine can be generated.
3. Use get_user_hair_profile to load the user's hair profile.
4. Use detect_climate_conflicts to check for weather-dependent conflicts. Pass the humidity value and the UV index from the weather data.
5. If any climate conflicts are found, use save_conflict_to_db to save each one.
6. Use generate_hair_routine to create a personalized routine. Pass weather_json (the weather data) and climate_conflicts_json.
7. Use save_routine_to_db to persist the routine (date_str="{date_str}").
8. CALENDAR CHECK: Review the generated routine. If it includes a wash day (is_wash_day=true) or any step that takes more than 10 minutes (like deep conditioning, protein treatment, or hair mask), use schedule_calendar_event to block time on the user's calendar.
   - Set event_title to something like "Wash Day Routine" or "Deep Conditioning Treatment"
   - Set event_description to a summary of the routine steps
   - Set duration_minutes based on the total routine time
   - Set date_str to "{date_str}"
9. Provide a final summary of the routine generated and any calendar events scheduled."""

    result = await run_agent_loop(goal, NIGHTLY_ROUTINE_TOOLS, user_id, pipeline_name)

    log_pipeline_event(
        user_id, pipeline_name,
        f"Routine pipeline complete for {date_str}: {result.get('summary', 'done')[:200]}",
        status="success",
    )

    return result