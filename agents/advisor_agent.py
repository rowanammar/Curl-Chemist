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
    Location: {profile.get('location', {}).get('city', 'Unknown')}
    Goals: {', '.join(profile.get('goals', []))}
    
    Current Shelf (Products):
    """
    if products:
        for p in products:
            context_str += f"- {p.get('name')} (Brand: {p.get('brand')})\n"
    else:
        context_str += "No products on shelf.\n"
        
    context_str += "\nRecent Wash History (last 3):\n"
    if wash_history:
        for w in wash_history[:3]:
            context_str += f"- Date: {w.get('date')}, Frizz: {w.get('analysis', {}).get('frizz_level', '?')}/10, Definition: {w.get('analysis', {}).get('curl_definition', '?')}/10\n"
    else:
        context_str += "No wash history logged yet.\n"

    system_prompt = f"""You are the Curl Advisor, a specialized, highly intelligent AI hair care assistant.
Your job is to answer the user's questions about hair care, styling, product recommendations, and routines.

{context_str}

STRICT BOUNDARIES:
1. You MUST ONLY answer questions related to hair care, beauty, skincare, or personal grooming.
2. If the user asks a question completely unrelated to hair/beauty (e.g., math problems, coding, politics, general trivia), you MUST politely refuse to answer and remind them that you are a specialized hair care advisor.
3. Be friendly, empathetic, and professional. 
4. Always reference the user's specific hair profile or products if relevant to their question.
5. Use plain text formatting or markdown (bullet points, bold text). Do not use emojis unless absolutely necessary for tone (keep it minimal).

Refusal Example: "I'm your Curl Advisor, so I'm strictly focused on hair and beauty! I can't help with math equations, but I'd love to talk about your hair goals."
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
