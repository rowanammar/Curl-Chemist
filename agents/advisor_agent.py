"""
Advisor Agent — Personalized Hair Care Chat with Gemma Intent Router.

ARCHITECTURE:
1. User message → Gemma (fast, cheap) classifies intent
2. If off-topic → immediate refusal (skip expensive Gemini call)
3. If hair-care → route to Gemini 3.5 for full response

WHY GEMMA:
- Hackathon rubric awards 0.2 bonus points for using a secondary Google AI model
- Gemma-3-4b-it is ultra-fast (<200ms) and perfect for binary classification
- Saves Gemini 3.5 tokens on off-topic messages
"""

import json
from typing import Dict, Any, List
from google import genai
from google.genai import types
from config import GEMINI_MODEL, GEMMA_MODEL, GCP_PROJECT_ID, GCP_REGION, GEMINI_API_KEY

def get_client() -> genai.Client:
    if GEMINI_API_KEY:
        return genai.Client(api_key=GEMINI_API_KEY)
    return genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)


# ══════════════════════════════════════════════
# GEMMA INTENT ROUTER — fast, cheap pre-filter
# ══════════════════════════════════════════════

async def classify_intent(client: genai.Client, user_message: str) -> dict:
    """
    Use Gemma as a fast intent classifier / safety filter.

    Classifies the user's message BEFORE routing to the expensive
    Gemini 3.5 model. Returns the intent category and confidence.

    Returns:
        dict with:
        - intent: "hair_care" | "off_topic" | "greeting" | "unclear"
        - confidence: float 0.0-1.0
        - reason: brief explanation
    """
    try:
        response = await client.aio.models.generate_content(
            model=GEMMA_MODEL,
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(text=f"""Classify this user message into exactly one category.

MESSAGE: "{user_message}"

CATEGORIES:
- "hair_care": Questions about hair, curls, products, ingredients, routines, styling, scalp care, beauty, skincare, or personal grooming
- "greeting": Simple greetings like "hi", "hello", "hey", "what can you do"
- "off_topic": Completely unrelated questions (math, coding, politics, cooking non-beauty items, etc.)
- "unclear": Cannot determine intent

Return ONLY a JSON object with keys: "intent", "confidence" (0.0-1.0), "reason" (brief explanation).
""")])
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        result = json.loads(response.text)
        # Ensure required keys exist
        return {
            "intent": result.get("intent", "unclear"),
            "confidence": float(result.get("confidence", 0.5)),
            "reason": result.get("reason", ""),
        }
    except Exception as e:
        # If Gemma fails, default to routing through (fail-open)
        print(f"Gemma intent classification failed: {e}")
        return {"intent": "hair_care", "confidence": 0.0, "reason": f"Gemma unavailable: {e}"}


# ══════════════════════════════════════════════
# MAIN ADVISOR — Gemini 3.5 response generation
# ══════════════════════════════════════════════

async def generate_advisor_response(
    username: str, 
    user_context: Dict[str, Any], 
    chat_history: List[Dict[str, str]], 
    user_message: str
) -> str:
    """
    Generates a response from the AI Advisor.
    
    Flow:
    1. Gemma classifies intent (< 200ms, cheap)
    2. If off-topic with high confidence → immediate refusal
    3. If hair-care or greeting → route to Gemini 3.5
    """
    client = get_client()

    # ── Step 1: Gemma Intent Router ──
    intent_result = await classify_intent(client, user_message)
    intent = intent_result.get("intent", "unclear")
    confidence = intent_result.get("confidence", 0.0)

    # Log the intent classification for observability
    print(f"[GEMMA ROUTER] intent={intent}, confidence={confidence}, reason={intent_result.get('reason', '')}")

    # ── Step 2: Gate off-topic messages ──
    if intent == "off_topic" and confidence >= 0.8:
        return (
            "I appreciate the question, but I'm specifically designed to help with "
            "**hair care, styling, product analysis, and beauty routines**. "
            "I can't help with that topic, but I'd love to answer any hair-related questions you have!\n\n"
            f"*— Filtered by Gemma intent router (confidence: {confidence:.0%})*"
        )

    # ── Step 3: Build context for Gemini 3.5 ──
    # Format context for the prompt
    profile = user_context.get("profile", {})
    products = user_context.get("products", [])
    wash_history = user_context.get("wash_history", [])
    routine = user_context.get("routine", {})

    context_str = f"""
    --- USER CONTEXT ---
    Username: {username}
    Hair Type: {profile.get('hair_type', 'Unknown')}
    Porosity: {profile.get('porosity', 'Unknown')}
    Protein Sensitivity: {profile.get('protein_sensitivity', 'Unknown')}
    Thickness: {profile.get('thickness', 'Unknown')}
    Location: {profile.get('location', {}).get('city', 'Unknown')}, {profile.get('location', {}).get('country', 'Unknown')}
    Goals: {', '.join(profile.get('goals', []))}
    
    Current Shelf (Products):
    """
    if products:
        for p in products:
            context_str += f"- {p.get('product_name', 'Unknown')} (Brand: {p.get('brand', 'Unknown')}, Category: {p.get('product_type', 'Unknown')})\n"
    else:
        context_str += "No products on shelf.\n"
        
    context_str += "\nRecent Wash History (last 3):\n"
    if wash_history:
        for w in wash_history[:3]:
            notes = w.get('notes', 'No notes.')
            frizz = w.get('analysis', {}).get('frizz_level', '?')
            curl = w.get('analysis', {}).get('curl_definition', '?')
            photo = "Yes" if w.get("photo_url") else "No"
            context_str += f"- Date: {w.get('date')}, Frizz: {frizz}/10, Definition: {curl}/10, Photo Uploaded: {photo}, Notes: {notes}\n"
    else:
        context_str += "No wash history logged yet.\n"

    system_prompt = f"""You are the Curl Advisor, a specialized, highly intelligent AI hair care assistant.
Your job is to answer the user's questions about hair care, styling, product recommendations, and routines.

{context_str}

STRICT BOUNDARIES & RULES:
1. You MUST ONLY answer questions related to hair care, beauty, skincare, or personal grooming.
2. If the user asks a completely unrelated question, politely refuse and remind them of your specialty.
3. LOCALITY RULE: When recommending any products (shampoo, dye, styling, etc.), you MUST ONLY recommend products that are widely and easily available in the user's location ({profile.get('location', {}).get('city', 'Unknown')}). For example, if they are in Egypt, do not recommend US-only stores like Ulta, Target, or Sally Beauty. Suggest local pharmacies, local brands, or international brands widely available in their specific country.
4. Always reference the user's specific hair profile, shelf products, or wash history if relevant.
5. Use markdown (bullet points, bold text). Do not use emojis unless absolutely necessary.
"""

    # Format chat history for Gemini
    contents = []
    for msg in chat_history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
    
    # Add current message
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7,
    )

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        )
        return response.text
    except Exception as e:
        print(f"Error in advisor agent: {e}")
        return "I'm having a little trouble connecting to my lab right now. Please try asking again in a moment."
