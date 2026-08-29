"""
Advisor Agent — Personalized Hair Care Chat
Uses Gemini to answer hair/beauty queries while enforcing strict boundaries.
"""

from typing import Dict, Any, List
from google import genai
from google.genai import types
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION, GEMINI_API_KEY

def get_client() -> genai.Client:
    if GEMINI_API_KEY:
        return genai.Client(api_key=GEMINI_API_KEY)
    return genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)

async def generate_advisor_response(
    username: str, 
    user_context: Dict[str, Any], 
    chat_history: List[Dict[str, str]], 
    user_message: str
) -> str:
    """
    Generates a response from the AI Advisor.
    """
    client = get_client()

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
