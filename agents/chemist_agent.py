"""
Chemist Agent — Detects ingredient conflicts between products.

WHAT THIS AGENT DOES:
1. Takes the full product shelf (all products + their ingredients)
2. Runs every product pair through the conflict rule engine
3. Returns a list of conflicts with severity and explanations

HOW THE CONFLICT DETECTION WORKS:
- First: check against the static rule engine (conflict_rules.json)
  This catches known, proven conflicts. It's fast and reliable.
- Then: use Gemini ONLY to personalize the explanation for the user's
  specific products. Gemini does NOT invent conflicts from scratch.
  This prevents hallucinated conflicts.
"""

import json
from pathlib import Path
# pyrefly: ignore [missing-import]
from google import genai
from google.genai import types
from google.adk import Agent
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION, GEMINI_API_KEY

# Load conflict rules once at startup
RULES_PATH = Path(__file__).parent.parent / "data" / "conflict_rules.json"
with open(RULES_PATH) as f:
    CONFLICT_RULES = json.load(f)

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)

CHEMIST_INSTRUCTION = """You are the Chemist Agent of Curl Chemist.

Your job: Analyze ingredient interactions between products on the user's shelf.

IMPORTANT RULES:
- You ONLY flag conflicts that match the known conflict rule engine.
- You do NOT invent new conflict types. If it's not in the rules, don't flag it.
- You personalize the explanation to mention the specific product names and ingredients.
- Severity levels: "critical" (🔴), "warning" (🟡), "info" (🟢)
"""


async def check_product_conflicts(products: list[dict]) -> list[dict]:
    """
    Passes the entire shelf + the conflict rule concepts to Gemini to find holistic, non-hallucinated conflicts.
    """
    if len(products) == 0:
        return []

    # Simplify product list to text for prompt
    shelf_text = "USER'S SHELF:\n"
    for p in products:
        shelf_text += f"- Product ID: {p['id']}, Name: {p.get('product_name', 'Unknown')}\n"
        shelf_text += f"  Ingredients: {', '.join([i.get('inci', i.get('name', '')) for i in p.get('ingredients', [])])}\n\n"

    # Load rules text for context, filtering out climate rules to avoid LLM weather hallucinations
    filtered_rules = [r for r in CONFLICT_RULES if r.get("type") != "climate_interaction"]
    rules_text = json.dumps(filtered_rules, indent=2)

    prompt = f"""You are a Master Cosmetic Chemist. Here is the user's product shelf, and a rulebook of scientifically proven conflict concepts (like Silicone Buildup, Protein Overload, etc).

1. RULEBOOK STRICTNESS: You ONLY flag conflicts that are fundamentally based on the concepts in the provided rulebook. DO NOT invent new conflict concepts that have no basis in the rules.
2. INTELLIGENT APPLICATION: You are an agent, not a dumb script. Apply the rules intelligently based on their underlying chemistry. For example, if a rule states that a sulfate-free cleanser cannot wash out heavy silicones, you must logically deduce that having NO cleanser at all will cause the exact same (or worse) silicone buildup, and flag it under that rule.
3. Apply common sense. Trace Citric Acid is a pH adjuster, not a chemical peel (ignore).
4. MITIGATION EXCEPTION: If a conflict rule says Product A cannot be removed by Product B, but the user ALSO has a mitigating product on their shelf (like a clarifying shampoo with sulfates), DO NOT flag the conflict. The user already has the solution on their shelf!
5. ABSENCE CONDITION EVALUATION: If a rule triggers on the absence of a product, you must carefully verify that NO product on the entire shelf can act as that product before flagging it.
6. EXCLUSIONS: DO NOT flag conflicts based on weather/climate (like humidity/UV). DO NOT flag conflicts based on hair porosity/type unless explicitly provided.

{shelf_text}

RULEBOOK:
{rules_text}

Return a JSON array of conflict objects. Each object must have exactly these keys:
- "product_a_id": string (the ID of the first conflicting product)
- "product_a_name": string (the name of the first conflicting product)
- "product_b_id": string (the ID of the second conflicting product, or empty if it's a shelf-wide issue)
- "product_b_name": string (the name of the second conflicting product, or empty)
- "severity": string (either "critical", "warning", or "info")
- "explanation": string (A personalized explanation mentioning specific ingredients)
- "fix": string (Actionable advice to fix it)
"""

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini holistic conflict detection failed: {e}")
        return []


def _ingredient_matches_category(ingredient: dict, trigger: dict) -> str | None:
    """Check if an ingredient matches a rule trigger."""
    name = ingredient.get("name", "").lower()
    inci = ingredient.get("inci", "").lower()
    
    examples = [e.lower() for e in trigger.get("examples", [])]
    
    for ex in examples:
        if ex in name or ex in inci:
            return name or inci
    return None

def check_climate_conflicts(
    products: list[dict], humidity: float, uv_index: float
) -> list[dict]:
    """
    Check for climate-dependent conflicts.
    These are conflicts that only apply under certain weather conditions.
    """
    climate_conflicts = []

    for rule in CONFLICT_RULES:
        condition = rule.get("condition")
        if not condition:
            continue

        # Check humidity conditions
        should_check = False
        if condition == "humidity_above_65" and humidity > 65:
            should_check = True
        elif condition == "humidity_below_30" and humidity < 30:
            should_check = True
        elif condition == "uv_index_above_7_and_no_uv_filter" and uv_index > 7:
            should_check = True

        if not should_check:
            continue

        for product in products:
            for ingredient in product.get("ingredients", []):
                match = _ingredient_matches_category(ingredient, rule["trigger_a"])
                if match:
                    climate_conflicts.append({
                        "rule_id": rule["id"],
                        "type": rule["type"],
                        "severity": rule["severity"],
                        "product_name": product.get("product_name", "Unknown"),
                        "product_id": product["id"],
                        "ingredient": match,
                        "condition": condition,
                        "explanation": rule["explanation"].replace("{a}", match),
                        "fix": rule["fix"],
                    })

    return climate_conflicts


# Define the ADK agent
chemist_agent = Agent(
    name="chemist",
    model=GEMINI_MODEL,
    instruction=CHEMIST_INSTRUCTION,
    tools=[check_product_conflicts, check_climate_conflicts],
)