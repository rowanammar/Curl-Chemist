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


def check_condition(condition: str, products: list[dict], profile: dict = None) -> bool:
    if not condition:
        return True
    
    profile = profile or {}

    if condition == "no_sulfate_cleanser_in_shelf":
        sulfate_examples = ["sodium lauryl sulfate", "sodium laureth sulfate", "ammonium lauryl sulfate", "ammonium laureth sulfate", "sodium coco sulfate", "tea-lauryl sulfate"]
        for p in products:
            for ing in p.get("ingredients", []):
                name = ing.get("name", "").lower()
                inci = ing.get("inci", "").lower()
                if any(s in name or s in inci for s in sulfate_examples):
                    return False
        return True

    if condition == "no_deep_conditioner_in_shelf":
        for p in products:
            ptype = p.get("product_type", "").lower()
            name = p.get("product_name", "").lower()
            if "deep conditioner" in ptype or "mask" in ptype or "treatment" in ptype:
                return False
        return True
        
    if condition == "no_heat_protectant_in_shelf":
        for p in products:
            ptype = p.get("product_type", "").lower()
            if "heat protectant" in ptype or "protectant" in ptype:
                return False
        return True
    
    if condition == "damaged_or_dry_hair":
        goals = [g.lower() for g in profile.get("goals", [])]
        return "repair damage" in goals or "add moisture" in goals or any("damaged" in g for g in goals)

    if condition == "color_treated_hair":
        color_history = str(profile.get("color_history", "")).lower()
        return "yes" in color_history or "dyed" in color_history or "bleached" in color_history or "color" in color_history or "highlighted" in color_history

    if condition == "low_porosity_hair":
        return str(profile.get("porosity", "")).lower() == "low"
    
    return True

def _product_has_trigger(product: dict, trigger: dict) -> str | None:
    for ingredient in product.get("ingredients", []):
        match = _ingredient_matches_category(ingredient, trigger)
        if match:
            return match
    return None

async def check_product_conflicts(products: list[dict], user_id: str = None) -> list[dict]:
    """
    Evaluates the shelf programmatically against conflict_rules.json to guarantee 
    consistency and reproducibility, then uses Gemini to intelligently consolidate.
    """
    if len(products) == 0:
        return []

    from firestore_helpers import get_user_profile
    profile = get_user_profile(user_id) if user_id else {}

    raw_conflicts = []
    seen = set()
    
    # Filter out climate rules, they are evaluated separately
    rules = [r for r in CONFLICT_RULES if r.get("type") != "climate_interaction"]
    
    for rule in rules:
        trigger_a = rule.get("trigger_a")
        trigger_b = rule.get("trigger_b")
        condition = rule.get("condition")
        
        if trigger_a and trigger_b:
            for i, pA in enumerate(products):
                match_a = _product_has_trigger(pA, trigger_a)
                if not match_a: continue
                
                for j, pB in enumerate(products):
                    if i == j: continue
                    match_b = _product_has_trigger(pB, trigger_b)
                    if not match_b: continue
                    
                    if not check_condition(condition, products, profile):
                        continue
                        
                    # Deduplicate by sorting IDs
                    id_pair = tuple(sorted([pA["id"], pB["id"]]))
                    uniq_key = (rule["id"], id_pair)
                    if uniq_key in seen:
                        continue
                    seen.add(uniq_key)
                        
                    raw_conflicts.append({
                        "product_a_id": pA["id"],
                        "product_a_name": pA.get("product_name", "Unknown"),
                        "product_b_id": pB["id"],
                        "product_b_name": pB.get("product_name", "Unknown"),
                        "rule_id": rule["id"],
                        "severity": rule["severity"],
                        "explanation": rule["explanation"].replace("{a}", match_a).replace("{b}", match_b),
                        "fix": rule["fix"]
                    })
        elif trigger_a:
            for pA in products:
                match_a = _product_has_trigger(pA, trigger_a)
                if not match_a: continue
                
                if not check_condition(condition, products, profile):
                    continue
                    
                uniq_key = (rule["id"], pA["id"])
                if uniq_key in seen:
                    continue
                seen.add(uniq_key)
                    
                raw_conflicts.append({
                    "product_a_id": pA["id"],
                    "product_a_name": pA.get("product_name", "Unknown"),
                    "product_b_id": "",
                    "product_b_name": "",
                    "rule_id": rule["id"],
                    "severity": rule["severity"],
                    "explanation": rule["explanation"].replace("{a}", match_a),
                    "fix": rule["fix"]
                })
                
    if not raw_conflicts:
        return []

    # Use Gemini to deduplicate and resolve contradictions intelligently
    prompt = f"""You are a Master Cosmetic Chemist. I have run a deterministic rule engine against the user's shelf and found these raw conflicts:
    
{json.dumps(raw_conflicts, indent=2)}

Your job is to CONSOLIDATE, DEDUPLICATE, and RESOLVE CONTRADICTIONS to produce a clean, finalized list of conflicts for the user.
1. CONSOLIDATION (CRITICAL): Do NOT output the same warning multiple times for different products. If multiple products trigger the exact same rule (e.g. 3 products have drying alcohol, or 3 products clash with the alkaline shampoo), COMBINE them into a SINGLE conflict. List all affected products separated by commas in `product_a_name` and `product_a_id` (e.g. "Mask, Gel, Conditioner"). 
2. RESOLVE CONTRADICTIONS: If `sulfate_color_treated` is flagged (because they have sulfates) BUT they also have non-water-soluble silicones on their shelf (which REQUIRE sulfates to wash out, meaning `silicone_buildup` would trigger without them), you must prioritize the silicone issue or explain the trade-off intelligently in a single combined conflict. Do not give contradictory advice.
3. OUTPUT FORMAT: Return a JSON array of conflict objects. Each object must have exactly these keys:
- "product_a_id": string (comma-separated IDs if consolidated)
- "product_a_name": string (comma-separated names if consolidated)
- "product_b_id": string (or empty)
- "product_b_name": string (or empty)
- "rule_id": string
- "severity": string ("critical", "warning", or "info")
- "explanation": string (A personalized, consolidated explanation)
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
        text = response.text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        print(f"Gemini conflict consolidation failed: {e}")
        return raw_conflicts


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
    products: list[dict], humidity: float, uv_index: float, user_city: str
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
                        "explanation": rule["explanation"].replace("{a}", match).format(user_city=user_city),
                        "fix": rule["fix"].format(user_city=user_city) if "{user_city}" in rule.get("fix", "") else rule["fix"],
                    })

    return climate_conflicts
