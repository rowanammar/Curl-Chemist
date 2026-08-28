import httpx
from google import genai
from google.adk import Agent
from config import (
    GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION,
    CAIRO_LAT, CAIRO_LON, WEATHER_API_URL,
)

client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)

CLIMATE_INSTRUCTION = """You are the Climate Agent of Curl Chemist.

Your job: Generate personalized daily hair care routines based on weather conditions
and the user's product shelf.

You consider:
- Humidity: affects humectant behavior (>65% = skip glycerin, <30% = seal with oils)
- UV Index: above 7 = recommend UV protection or physical cover
- Temperature: hot = lighter products, cold = heavier creams
- Dew point: the true measure of moisture in air (more reliable than humidity %)

You generate step-by-step routines with:
- Specific product names from the user's shelf
- Application amounts (e.g., "quarter-sized amount")
- Wait times between steps (e.g., "let sit 5 minutes under a cap")
- Technique notes (e.g., "scrunch, don't rub")

IMPORTANT: Never recommend products NOT on the user's shelf.
Only work with what they have.
"""


async def fetch_cairo_weather() -> dict:
    """
    Fetch tomorrow's weather forecast for Cairo.

    Returns dict with: humidity, uv_index, temperature, dew_point,
    wind_speed, and a human-readable summary.
    """
    params = {
        "latitude": CAIRO_LAT,
        "longitude": CAIRO_LON,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "relative_humidity_2m_mean",
            "uv_index_max",
            "precipitation_probability_max",
            "wind_speed_10m_max",
        ],
        "hourly": ["dew_point_2m"],
        "timezone": "Africa/Cairo",
        "forecast_days": 2,  # Today + tomorrow
    }

    async with httpx.AsyncClient() as http_client:
        response = await http_client.get(WEATHER_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

    # Extract tomorrow's data (index 1)
    daily = data.get("daily", {})
    tomorrow_idx = 1 if len(daily.get("temperature_2m_max", [])) > 1 else 0

    # Average dew point for tomorrow's daytime hours (8AM-8PM)
    hourly_dew = data.get("hourly", {}).get("dew_point_2m", [])
    # Tomorrow's hours are indices 24-47 if we got 2 days of hourly data
    tomorrow_dew_hours = hourly_dew[24:48] if len(hourly_dew) > 24 else hourly_dew[:24]
    daytime_dew = tomorrow_dew_hours[8:20] if len(tomorrow_dew_hours) > 20 else tomorrow_dew_hours
    avg_dew_point = sum(daytime_dew) / len(daytime_dew) if daytime_dew else 20.0

    weather = {
        "temperature_max": daily.get("temperature_2m_max", [30])[tomorrow_idx],
        "temperature_min": daily.get("temperature_2m_min", [20])[tomorrow_idx],
        "humidity": daily.get("relative_humidity_2m_mean", [50])[tomorrow_idx],
        "uv_index": daily.get("uv_index_max", [5])[tomorrow_idx],
        "precipitation_probability": daily.get("precipitation_probability_max", [0])[tomorrow_idx],
        "wind_speed": daily.get("wind_speed_10m_max", [10])[tomorrow_idx],
        "dew_point": round(avg_dew_point, 1),
    }

    return weather


async def generate_routine(products: list[dict], weather: dict, profile: dict) -> dict:
    """
    Generate a personalized daily routine using Gemini.

    Args:
        products: user's product shelf with ingredients
        weather: tomorrow's weather data
        profile: user's hair profile (type, porosity, goals)

    Returns:
        dict with steps, weather_summary, and climate_notes
    """
    from google.genai import types

    product_summaries = []
    for p in products:
        ing_names = [i["name"] for i in p.get("ingredients", [])[:5]]
        product_summaries.append(
            f"- {p.get('product_name', 'Unknown')} ({p.get('product_type', 'unknown')}): "
            f"key ingredients: {', '.join(ing_names)}"
        )

    adaptive = profile.get("adaptive_profile", {})
    adjustments = adaptive.get("routine_adjustments", [])
    adjustments_text = ""
    if adjustments:
        adjustments_text = "\nLEARNED PREFERENCES (Follow these above all else!):\n" + "\n".join(f"- {adj}" for adj in adjustments)

    prompt = f"""Generate a hair care routine for tomorrow based on this data.

WEATHER TOMORROW:
- Temperature: {weather['temperature_max']}°C high / {weather['temperature_min']}°C low
- Humidity: {weather['humidity']}%
- UV Index: {weather['uv_index']}
- Dew Point: {weather['dew_point']}°C
- Wind: {weather['wind_speed']} km/h
- Rain chance: {weather['precipitation_probability']}%

USER'S HAIR PROFILE:
- Hair type: {profile.get('hair_type', 'wavy')}
- Porosity: {profile.get('porosity', 'medium')}
- Thickness: {profile.get('thickness', 'medium')}
- Current goals: {profile.get('goals', ['reduce frizz', 'improve definition'])}{adjustments_text}


AVAILABLE PRODUCTS:
{chr(10).join(product_summaries)}

RULES:
- Only recommend products from the list above
- If humidity > 65%: avoid glycerin and humectant-heavy products
- If humidity < 30%: seal moisture with oils/butters
- If UV > 7: recommend UV protection or physical cover
- Application order: cleanser → treatment → leave-in → styler → sealant
- Include specific amounts and technique notes

Return a JSON object with:
- "summary": one-line weather-based summary (e.g., "High humidity day — anti-frizz protocol")
- "is_wash_day": true/false recommendation
- "steps": array of objects with "order", "action", "product_name", "amount", "technique", "wait_minutes"
- "climate_notes": array of strings explaining why specific choices were made
"""

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Part.from_text(prompt)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    import json
    return json.loads(response.text)


# Define the ADK agent
climate_agent = Agent(
    name="climate",
    model=GEMINI_MODEL,
    instruction=CLIMATE_INSTRUCTION,
    tools=[fetch_cairo_weather, generate_routine],
)