from datetime import datetime, timedelta, timezone
from agents.climate_agent import fetch_cairo_weather, generate_routine
from agents.chemist_agent import check_climate_conflicts
from firestore_helpers import (
    get_all_products, get_user_profile, save_routine,
    log_pipeline_event, save_conflict,
)


async def run_nightly_routine_pipeline():
    """
    Execute the nightly routine generation pipeline.

    This is called by the /pipelines/nightly endpoint when
    Cloud Scheduler fires at 9 PM.
    """
    pipeline_name = "nightly_routine"

    try:
        log_pipeline_event(pipeline_name, "Pipeline triggered by Cloud Scheduler")

        # Step 1: Fetch weather
        log_pipeline_event(pipeline_name, "Fetching tomorrow's Cairo weather...")
        weather = await fetch_cairo_weather()
        log_pipeline_event(
            pipeline_name,
            f"Weather fetched: {weather['humidity']}% humidity, "
            f"UV {weather['uv_index']}, {weather['temperature_max']}°C"
        )

        # Step 2: Load products
        products = get_all_products()
        if not products:
            log_pipeline_event(
                pipeline_name,
                "No products on shelf — skipping routine generation",
                status="warning",
            )
            return {"status": "skipped", "reason": "no_products"}

        log_pipeline_event(pipeline_name, f"Loaded {len(products)} products from shelf")

        # Step 3: Load profile
        profile = get_user_profile() or {
            "hair_type": "2B wavy",
            "porosity": "medium",
            "goals": ["reduce frizz", "improve definition"],
        }

        # Step 4: Check climate conflicts
        climate_conflicts = check_climate_conflicts(
            products, weather["humidity"], weather["uv_index"]
        )
        if climate_conflicts:
            log_pipeline_event(
                pipeline_name,
                f"Found {len(climate_conflicts)} climate-dependent conflicts",
                status="warning",
            )
            for conflict in climate_conflicts:
                save_conflict(conflict)

        # Step 5: Generate routine (pass conflicts so Gemini avoids those products)
        log_pipeline_event(pipeline_name, "Generating routine via Gemini...")
        routine = await generate_routine(products, weather, profile, climate_conflicts=climate_conflicts)

        # Step 6: Save routine
        # Use tomorrow's date as the document ID → idempotent
        from zoneinfo import ZoneInfo
        cairo_tz = ZoneInfo("Africa/Cairo")
        tomorrow = datetime.now(cairo_tz) + timedelta(days=1)
        date_str = tomorrow.strftime("%Y-%m-%d")

        routine_data = {
            "date": date_str,
            "weather": weather,
            "climate_conflicts": climate_conflicts,
            **routine,
        }
        save_routine(date_str, routine_data)

        log_pipeline_event(
            pipeline_name,
            f"Routine generated and saved for {date_str}",
            status="success",
        )

        return {"status": "success", "date": date_str, "routine": routine_data}

    except Exception as e:
        log_pipeline_event(pipeline_name, f"Pipeline failed: {str(e)}", status="error")
        raise