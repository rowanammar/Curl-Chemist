from google import genai
from google.genai import types
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION, GEMINI_API_KEY
from agents.profiler_agent import compute_trends
from firestore_helpers import (
    get_recent_wash_history, save_weekly_report,
    get_user_profile, save_user_profile,
    log_pipeline_event,
)
from datetime import datetime, timezone

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)


async def run_weekly_health_pipeline(user_id: str):
    """Execute the weekly hair health analysis pipeline for a specific user."""
    pipeline_name = "weekly_health"

    try:
        log_pipeline_event(user_id, pipeline_name, "Weekly health analysis triggered")

        # Step 1: Get recent wash history
        history = get_recent_wash_history(user_id, days=7)
        if len(history) < 1:
            log_pipeline_event(
                user_id, pipeline_name,
                "No wash entries this week — skipping analysis",
                status="warning",
            )
            return {"status": "skipped", "reason": "no_data"}

        log_pipeline_event(user_id, pipeline_name, f"Analyzing {len(history)} wash entries from this week")

        # Step 2: Compute trends
        trend_data = compute_trends(history)
        log_pipeline_event(
            user_id, pipeline_name,
            f"Trends computed: {trend_data.get('trends', {})}"
        )

        # Step 3: Generate insights via Gemini
        log_pipeline_event(user_id, pipeline_name, "Generating insights via Gemini...")

        # Build context for Gemini
        history_summary = []
        for entry in history:
            analysis = entry.get("analysis", {})
            weather = entry.get("weather_that_day", {})
            products = entry.get("products_used", [])
            history_summary.append(
                f"Date: {entry.get('date', 'unknown')}, "
                f"Frizz: {analysis.get('frizz_level', '?')}, "
                f"Definition: {analysis.get('curl_definition', '?')}, "
                f"Humidity: {weather.get('humidity', '?')}%, "
                f"Products: {', '.join(products) if products else 'unknown'}"
            )

        prompt = f"""Analyze this week's hair health data and generate actionable insights.

WEEKLY DATA:
{chr(10).join(history_summary)}

COMPUTED TRENDS:
{trend_data}

Generate 3-5 specific, actionable insights. Examples:
- "Curl definition improved on days when you used [product X] but not [product Y]"
- "Frizz was worst on high-humidity days when you used glycerin-based products"
- "Your best hair day was [date] — you used [products] in [weather conditions]"

Also suggest 1-2 routine adjustments based on the data.

Return JSON with keys: "insights" (array of strings), "routine_adjustments" (array of strings),
"best_day" (date string), "worst_day" (date string).
"""

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Part.from_text(text=prompt)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

        import json
        insights = json.loads(response.text)

        # Step 4: Update adaptive profile with learned preferences
        profile = get_user_profile(user_id) or {}
        adaptive = profile.get("adaptive_profile", {})

        # Store this week's adjustments in the long-term profile
        adaptive["last_weekly_analysis"] = datetime.now(timezone.utc).isoformat()
        adaptive["latest_trends"] = trend_data.get("trends", {})
        adaptive["routine_adjustments"] = insights.get("routine_adjustments", [])

        save_user_profile(user_id, {"adaptive_profile": adaptive})

        log_pipeline_event(
            user_id, pipeline_name,
            "Adaptive profile updated with this week's learnings"
        )

        # Step 5: Save weekly report
        now = datetime.now(timezone.utc)
        week_str = now.strftime("%Y-W%W")

        report = {
            "period": f"Week of {now.strftime('%B %d, %Y')}",
            "entry_count": len(history),
            "trends": trend_data,
            "insights": insights.get("insights", []),
            "routine_adjustments": insights.get("routine_adjustments", []),
            "best_day": insights.get("best_day"),
            "worst_day": insights.get("worst_day"),
        }

        save_weekly_report(user_id, week_str, report)

        log_pipeline_event(
            user_id, pipeline_name,
            f"Weekly report saved: {len(insights.get('insights', []))} insights generated",
            status="success",
        )

        return {"status": "success", "report": report}

    except Exception as e:
        log_pipeline_event(user_id, pipeline_name, f"Pipeline failed: {str(e)}", status="error")
        raise