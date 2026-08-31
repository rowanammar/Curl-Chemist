"""
Scanner Agent — Reads product labels via Gemini Vision.

WHAT THIS AGENT DOES:
1. Accepts product input in 3 ways: photo, product name, or manual ingredient text
2. Extracts structured ingredient data using Gemini
3. Validates whether the product is actually a hair/scalp product
4. Returns structured data for user review before saving to shelf

INPUT MODES:
- scan_product_from_bytes(): User uploads a photo directly from the dashboard
- scan_product_by_name(): User types a product name, Gemini looks up ingredients
- scan_product_from_text(): User pastes/types an ingredient list manually
- scan_product_label(): Legacy — accepts a GCS URI (used by Pub/Sub pipeline)
"""

import json
import base64
from google import genai
from google.genai import types
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION, GEMINI_API_KEY
from firestore_helpers import get_part_from_gcs_uri

# Initialize the Gemini client via Vertex AI
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)

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

# ── Shared JSON schema for all scan methods ──

SCAN_RESPONSE_SCHEMA = """Return a JSON object with these keys:
- "product_name": string
- "brand": string
- "product_type": string (shampoo, conditioner, leave-in, gel, mask, serum, oil, cream, spray, or other)
- "is_hair_product": boolean (true if this is a hair/scalp care product)
- "product_category_detected": string (what kind of product this actually is, e.g. "shampoo", "dish soap", "sunscreen", "body lotion")
- "confidence": float 0-1 (how confident you are in the extraction)
- "ingredients": array of objects, each with:
    - "name": string (as written on label)
    - "inci": string (INCI standard name)
    - "category": one of ["silicone", "protein", "humectant", "oil", "butter", "sulfate", "preservative", "fragrance", "emulsifier", "thickener", "hold_polymer", "conditioning_polymer", "drying_alcohol", "fatty_alcohol", "wax", "mineral_oil", "uv_filter", "acidic_treatment", "alkaline_product", "other"]
    - "needs_review": boolean (true if uncertain about this ingredient)
"""


async def scan_product_from_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Scan a product label from raw image bytes (direct upload from dashboard).

    This is the PRIMARY method for local development and dashboard use.
    No Cloud Storage needed.

    Args:
        image_bytes: Raw bytes of the product photo
        mime_type: MIME type of the image (default: image/jpeg)

    Returns:
        dict with product_name, brand, product_type, is_hair_product, ingredients list
    """
    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            types.Part.from_text(
                text="Extract all ingredients from this product label photo. "
                "Handle Arabic, English, and mixed-language text. "
                "If uncertain about any ingredient, set needs_review to true.\n\n"
                "IMPORTANT: Also determine if this is a hair/scalp care product "
                "or something else (dish soap, sunscreen, body lotion, etc).\n\n"
                + SCAN_RESPONSE_SCHEMA
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    text = response.text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return json.loads(text.strip())


async def scan_product_by_name(product_name: str) -> dict:
    """
    Look up a product's ingredients by name using Gemini's knowledge.

    The AI recalls the product's ingredient list from its training data.
    NOTE: This is NOT guaranteed to be perfectly accurate.
    All ingredients are marked as needs_review=true by default.

    Args:
        product_name: Full product name (e.g., "Shea Moisture Curl Enhancing Smoothie")

    Returns:
        dict with product_name, brand, product_type, is_hair_product, ingredients list
    """
    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_text(
                text=f"I need the full ingredient list for this hair care product: \"{product_name}\"\n\n"
                "Look up this product from your knowledge. If you know this product, "
                "return its complete ingredient list. If you're not sure about the exact "
                "formulation, return your best guess but mark ALL ingredients as needs_review: true.\n\n"
                "If you cannot identify this product at all, return an empty ingredients array "
                "and set confidence to 0.\n\n"
                "IMPORTANT: Also determine if this is a hair/scalp care product "
                "or something else entirely.\n\n"
                + SCAN_RESPONSE_SCHEMA
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    text = response.text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    result = json.loads(text.strip())

    # Safety: mark all AI-recalled ingredients as needing review
    for ing in result.get("ingredients", []):
        ing["needs_review"] = True

    # Add source metadata
    result["scan_method"] = "name_lookup"
    result["disclaimer"] = "Ingredients retrieved from AI memory — verify against your actual product label"

    return result


async def scan_product_from_text(product_name: str, ingredients_text: str) -> dict:
    """
    Parse a manually entered ingredient list into structured data.

    The user types or pastes the ingredient list (e.g., from a website or
    by reading the label). Gemini classifies each ingredient.

    Args:
        product_name: Name the user gives the product
        ingredients_text: Raw ingredient text (comma-separated, newline-separated, etc.)

    Returns:
        dict with product_name, brand, product_type, is_hair_product, ingredients list
    """
    from pipelines.input_sanitizer import InputSanitizer
    if await InputSanitizer.detect_prompt_injection(ingredients_text):
        return {"error": "Security policy violation: Prompt Injection blocked."}
    
    ingredients_text = InputSanitizer.scan_for_pii(ingredients_text)
    
    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_text(
                text=f"Product name: \"{product_name}\"\n\n"
                f"Here is the ingredient list the user provided:\n{ingredients_text}\n\n"
                "Parse and classify each ingredient. The input may be comma-separated, "
                "newline-separated, or in any format. Extract each individual ingredient.\n\n"
                "IMPORTANT: Also determine if this is a hair/scalp care product "
                "or something else entirely.\n\n"
                + SCAN_RESPONSE_SCHEMA
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    text = response.text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    result = json.loads(text.strip())
    result["scan_method"] = "manual_entry"
    return result


async def scan_product_label(image_uri: str) -> dict:
    """
    Scan a product label photo from a Cloud Storage URI.

    This is used by the Pub/Sub pipeline (Cloud Storage notification).
    For local/dashboard use, prefer scan_product_from_bytes().

    Args:
        image_uri: Google Cloud Storage URI (gs://bucket/path/to/photo.jpg)

    Returns:
        dict with product_name, brand, product_type, is_hair_product, ingredients list
    """
    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            get_part_from_gcs_uri(image_uri, mime_type="image/jpeg"),
            types.Part.from_text(
                text="Extract all ingredients from this product label photo. "
                "Handle Arabic, English, and mixed-language text. "
                "If uncertain about any ingredient, set needs_review to true.\n\n"
                "IMPORTANT: Also determine if this is a hair/scalp care product "
                "or something else entirely.\n\n"
                + SCAN_RESPONSE_SCHEMA
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    text = response.text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return json.loads(text.strip())


