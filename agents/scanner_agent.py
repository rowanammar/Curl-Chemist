
from google import genai
from google.adk import Agent
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION

# Initialize the Gemini client via Vertex AI
client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)

SCANNER_INSTRUCTION = """You are the Scanner Agent of Curl Chemist.

Your job: Extract and classify ingredients from hair/skincare product label photos.

When given a product photo:
1. Read the full ingredient list from the label (handle Arabic, English, or mixed text of any language)
2. For each ingredient, provide:
   - name: the ingredient name as written on the label
   - inci: the INCI (International Nomenclature of Cosmetic Ingredients) standard name
   - category: one of [silicone, protein, humectant, oil, butter, sulfate, preservative,
     fragrance, emulsifier, thickener, hold_polymer, conditioning_polymer, drying_alcohol,
     fatty_alcohol, wax, mineral_oil, uv_filter, acidic_treatment, alkaline_product, other]

3. Also extract: product name, brand name, and product type (shampoo, conditioner,
   leave-in, gel, mask, serum, oil, cream, spray)

If the label is unclear or you're not confident about an ingredient (confidence < 0.7),
mark it as "needs_review": true.

Return valid JSON only. No extra text.
"""


async def scan_product_label(image_uri: str) -> dict:
    """
    Scan a product label photo and extract structured ingredient data.

    Args:
        image_uri: Google Cloud Storage URI (gs://bucket/path/to/photo.jpg)

    Returns:
        dict with product_name, brand, product_type, ingredients list
    """
    from google.genai import types

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_uri(file_uri=image_uri, mime_type="image/jpeg"),
            types.Part.from_text(
                "Extract all ingredients from this product label photo. "
                "Return a JSON object with keys: product_name, brand, product_type, "
                "and ingredients (array of {name, inci, category, needs_review}). "
                "Handle Arabic and English text. If uncertain about any ingredient, "
                "set needs_review to true."
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,  # Low temp = more deterministic/accurate
        ),
    )

    import json
    return json.loads(response.text)


# Define the ADK agent
scanner_agent = Agent(
    name="scanner",
    model=GEMINI_MODEL,
    instruction=SCANNER_INSTRUCTION,
    tools=[scan_product_label],
)