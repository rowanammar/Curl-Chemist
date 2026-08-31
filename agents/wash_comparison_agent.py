"""
Wash Comparison Agent — Compares wash day photos across time.

WHAT THIS AGENT DOES:
1. Takes the current wash day analysis + photo URI
2. Fetches previous wash day entries (with their photo URIs, products, weather)
3. Sends everything to Gemini with a structured comparative prompt
4. Determines which products/techniques are working vs. not
5. Factors in climate differences to avoid false blame

KEY INSIGHT: A product isn't "bad" just because hair looked frizzy — if it was
95% humidity that day, the weather is to blame, not the product. This agent
accounts for that.
"""

import json
from google import genai
from google.genai import types
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION, GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else genai.Client(
    vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION
)

COMPARISON_INSTRUCTION = """You are the Wash Day Comparison Agent of Curl Chemist.

Your job: Compare hair photos and metrics across wash days to determine
what products and routines are working vs. not working.

CRITICAL RULE: Always factor in weather/climate when making judgments.
- A bad hair day during 90%+ humidity does NOT mean the products failed
- A great hair day during perfect weather does NOT mean the products are magic
- Look for patterns: does a product consistently help ACROSS different weather?

You compare:
- Hair scores (frizz, definition, shine, damage) across days
- Products used on each day
- Weather conditions on each day
- User notes and observations
"""


async def compare_wash_days(
    current_entry: dict,
    previous_entries: list[dict],
    user_profile: dict = None,
) -> dict:
    """
    Compare the current wash day with previous ones to find patterns.

    Args:
        current_entry: today's wash data with analysis, products, weather
        previous_entries: list of past wash entries
        user_profile: user's hair profile for context

    Returns:
        dict with comparison_insights, product_effectiveness,
        climate_adjusted_notes, recommendations
    """
    if not previous_entries:
        return {
            "status": "first_entry",
            "message": "This is your first wash day! We'll start tracking patterns from here.",
            "comparison_insights": [],
            "product_effectiveness": [],
            "recommendations": [],
        }

    # Build context for each wash day
    def summarize_entry(entry, label=""):
        analysis = entry.get("analysis", {})
        weather = entry.get("weather_that_day", {})
        products = entry.get("products_used", [])
        return (
            f"{label}Date: {entry.get('date', 'unknown')}\n"
            f"  Scores: frizz={analysis.get('frizz_level', '?')}, "
            f"definition={analysis.get('curl_definition', '?')}, "
            f"shine={analysis.get('shine', '?')}, "
            f"damage={analysis.get('damage_visible', '?')}\n"
            f"  Weather: humidity={weather.get('humidity', '?')}%, "
            f"temp={weather.get('temperature_max', '?')}°C, "
            f"UV={weather.get('uv_index', '?')}, "
            f"dew_point={weather.get('dew_point', '?')}°C\n"
            f"  Products: {', '.join(products) if products else 'unknown'}\n"
            f"  Notes: {entry.get('notes', 'none')}\n"
            f"  Observations: {analysis.get('observations', 'none')}"
        )

    current_summary = summarize_entry(current_entry, "TODAY's WASH: ")

    previous_summaries = []
    for i, entry in enumerate(previous_entries[:10]):  # Cap at 10 for token limits
        previous_summaries.append(summarize_entry(entry, f"DAY {i+1}: "))

    profile_context = ""
    if user_profile:
        profile_context = f"""
USER'S HAIR PROFILE:
- Hair type: {user_profile.get('hair_type', 'unknown')}
- Porosity: {user_profile.get('porosity', 'unknown')}
- Protein sensitivity: {user_profile.get('protein_sensitivity', 'unknown')}
- Thickness: {user_profile.get('thickness', 'unknown')}
"""

    prompt = f"""Compare today's wash day results with previous days and provide insights.

{current_summary}

PREVIOUS WASH DAYS (most recent first):
{chr(10).join(previous_summaries)}
{profile_context}

ANALYSIS RULES:
1. Compare scores across days — are things improving, declining, or stable?
2. Identify which PRODUCTS correlate with better scores
3. CRITICALLY: Adjust for weather! Don't blame a product for bad results on a 90% humidity day.
4. Look for patterns: "Every time you used X + Y together, definition improved"
5. Note if the user switched products — did the switch help or hurt?
6. Consider the user's hair type when making recommendations

Return a JSON object with:
- "vs_last_wash": a brief comparison with the most recent previous wash (1-2 sentences)
- "trend": "improving" | "stable" | "declining" | "mixed" — overall hair health direction
- "comparison_insights": array of strings (3-5 specific observations comparing days)
- "product_effectiveness": array of objects, each with "product_name", "verdict" ("working", "neutral", "not_working"), and "reasoning"
- "climate_adjusted_notes": array of strings explaining how weather affected results
- "best_combo": string describing the best product combination seen so far
- "recommendations": array of strings (2-3 actionable suggestions)
"""

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Part.from_text(text=prompt)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    return json.loads(response.text)


async def compare_wash_days_with_photos(
    current_photo_uri: str,
    current_entry: dict,
    previous_entries_with_photos: list[dict],
    user_profile: dict = None,
) -> dict:
    """
    Compare wash days using BOTH photos and metrics.

    This version sends actual photos to Gemini for visual comparison.
    Falls back to text-only comparison if photo access fails.

    Args:
        current_photo_uri: GCS URI of today's photo
        current_entry: today's wash data
        previous_entries_with_photos: past entries with photo_url fields
        user_profile: user's hair profile

    Returns:
        Comparison results dict
    """
    # Build photo parts for Gemini
    content_parts = []

    # Add current photo
    try:
        content_parts.append(
            types.Part.from_uri(file_uri=current_photo_uri, mime_type="image/jpeg")
        )
        content_parts.append(
            types.Part.from_text(text="[TODAY'S PHOTO - shown above]")
        )
    except Exception:
        content_parts.append(
            types.Part.from_text(text="[TODAY'S PHOTO - not available]")
        )

    # Add previous photos (up to 4 most recent to stay within limits)
    for i, entry in enumerate(previous_entries_with_photos[:4]):
        photo_url = entry.get("photo_url")
        if photo_url and photo_url.startswith("gs://"):
            try:
                content_parts.append(
                    types.Part.from_uri(file_uri=photo_url, mime_type="image/jpeg")
                )
                content_parts.append(
                    types.Part.from_text(text=f"[PREVIOUS DAY {i+1} PHOTO - {entry.get('date', 'unknown')}]")
                )
            except Exception:
                pass

    # Build the text context
    def summarize_entry(entry, label=""):
        analysis = entry.get("analysis", {})
        weather = entry.get("weather_that_day", {})
        products = entry.get("products_used", [])
        return (
            f"{label}Date: {entry.get('date', 'unknown')}\n"
            f"  Scores: frizz={analysis.get('frizz_level', '?')}, "
            f"definition={analysis.get('curl_definition', '?')}, "
            f"shine={analysis.get('shine', '?')}, "
            f"damage={analysis.get('damage_visible', '?')}\n"
            f"  Weather: humidity={weather.get('humidity', '?')}%, "
            f"temp={weather.get('temperature_max', '?')}°C, "
            f"UV={weather.get('uv_index', '?')}, "
            f"dew_point={weather.get('dew_point', '?')}°C\n"
            f"  Products: {', '.join(products) if products else 'unknown'}\n"
            f"  Notes: {entry.get('notes', 'none')}"
        )

    current_summary = summarize_entry(current_entry, "TODAY: ")
    previous_summaries = [
        summarize_entry(e, f"DAY {i+1}: ")
        for i, e in enumerate(previous_entries_with_photos[:10])
    ]

    profile_text = ""
    if user_profile:
        profile_text = (
            f"\nHAIR PROFILE: type={user_profile.get('hair_type', '?')}, "
            f"porosity={user_profile.get('porosity', '?')}, "
            f"protein_sensitivity={user_profile.get('protein_sensitivity', '?')}"
        )

    prompt = f"""You are an expert curly hair analyst. Compare the hair photos and data across wash days.

LOOK AT THE PHOTOS CAREFULLY — compare visible frizz, curl clumping, shine, and damage.

{current_summary}

PREVIOUS WASH DAYS:
{chr(10).join(previous_summaries)}
{profile_text}

RULES:
1. Compare what you SEE in the photos with the numerical scores
2. Factor in weather — don't blame products for weather-caused issues
3. Identify which product combinations give the best visual results
4. Be specific: "The curls in today's photo show tighter clumping compared to Day 2"

Return JSON with:
- "vs_last_wash": brief visual comparison with the most recent previous wash
- "trend": "improving" | "stable" | "declining" | "mixed"
- "comparison_insights": array of 3-5 specific visual + data observations
- "product_effectiveness": array of {{"product_name": str, "verdict": "working"|"neutral"|"not_working", "reasoning": str}}
- "climate_adjusted_notes": array of strings on how weather affected each day
- "best_combo": string — the best product combination seen
- "recommendations": array of 2-3 actionable suggestions
"""

    content_parts.append(types.Part.from_text(text=prompt))

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=content_parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
        return json.loads(response.text)
    except Exception:
        # Fall back to text-only comparison
        return await compare_wash_days(current_entry, previous_entries_with_photos, user_profile)


