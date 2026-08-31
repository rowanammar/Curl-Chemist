"""
Profiler Agent — Analyzes hair health trends from wash day photos.

WHAT THIS AGENT DOES:
1. Takes wash day photos and analyzes them via Gemini Vision
2. Scores: frizz level, curl definition, shine, visible damage (1-10 each)
3. Correlates scores with products used + weather that day
4. Detects trends and generates insights
5. Writes findings that Pipeline 3 uses to auto-adjust routines
"""

from google import genai
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION, GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)

PROFILER_INSTRUCTION = """You are the Profiler Agent of Curl Chemist.

Your job: Analyze hair selfie photos and track health trends over time.

When analyzing a photo, score these attributes (1-10):
- frizz_level: 1 = no frizz, 10 = extreme frizz
- curl_definition: 1 = no definition, 10 = perfect clumps
- shine: 1 = dull/matte, 10 = healthy shine
- damage_visible: 1 = no damage, 10 = severe damage visible

Be consistent across photos. Use the full range of the scale.
"""


async def analyze_hair_photo(image_uri: str) -> dict:
    """
    Analyze a hair selfie and return health scores.

    Args:
        image_uri: Cloud Storage URI of the hair photo

    Returns:
        dict with frizz_level, curl_definition, shine, damage_visible (all 1-10)
        plus observations (free text)
    """
    from google.genai import types

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_uri(file_uri=image_uri, mime_type="image/jpeg"),
            types.Part.from_text(
                text="I need you to act as a curly hair expert profiler. "
                "Score the following on a scale of 1-10: "
                "frizz_level (1=none, 10=extreme), curl_definition (1=none, 10=perfect), "
                "shine (1=dull, 10=healthy), damage_visible (1=none, 10=severe). "
                "Also provide brief observations about the hair condition. "
                "Return JSON with keys: frizz_level, curl_definition, shine, "
                "damage_visible, observations."
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    import json
    return json.loads(response.text)


def compute_trends(history: list[dict]) -> dict:
    """
    Compute health trends from wash history entries.

    Takes a list of wash history entries (each with analysis scores)
    and computes whether metrics are improving, declining, or stable.

    Args:
        history: list of wash entries, each with 'analysis' containing scores

    Returns:
        dict with trend direction per metric + insights
    """
    if len(history) < 2:
        return {"status": "insufficient_data", "message": "Need at least 2 wash entries for trends"}

    metrics = ["frizz_level", "curl_definition", "shine", "damage_visible"]
    trends = {}

    for metric in metrics:
        values = [
            entry.get("analysis", {}).get(metric, 5)
            for entry in history
            if entry.get("analysis", {}).get(metric) is not None
        ]
        if len(values) < 2:
            trends[metric] = "insufficient_data"
            continue

        # Simple trend: compare first half average to second half average
        mid = len(values) // 2
        first_half = sum(values[:mid]) / mid
        second_half = sum(values[mid:]) / len(values[mid:])
        diff = second_half - first_half

        if abs(diff) < 0.5:
            trends[metric] = "stable"
        elif diff > 0:
            # For frizz and damage, increasing is BAD. For definition and shine, it's GOOD.
            if metric in ("frizz_level", "damage_visible"):
                trends[metric] = "worsening"
            else:
                trends[metric] = "improving"
        else:
            if metric in ("frizz_level", "damage_visible"):
                trends[metric] = "improving"
            else:
                trends[metric] = "declining"

    # Compute averages
    averages = {}
    for metric in metrics:
        values = [
            entry.get("analysis", {}).get(metric, 5)
            for entry in history
            if entry.get("analysis", {}).get(metric) is not None
        ]
        averages[metric] = round(sum(values) / len(values), 1) if values else 5.0

    return {
        "trends": trends,
        "averages": averages,
        "entry_count": len(history),
    }


