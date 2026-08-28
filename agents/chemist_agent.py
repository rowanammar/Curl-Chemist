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
from google import genai
from google.adk import Agent
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION

# Load conflict rules once at startup
RULES_PATH = Path(__file__).parent.parent / "data" / "conflict_rules.json"
with open(RULES_PATH) as f:
    CONFLICT_RULES = json.load(f)

client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)

CHEMIST_INSTRUCTION = """You are the Chemist Agent of Curl Chemist.

Your job: Analyze ingredient interactions between products on the user's shelf.

IMPORTANT RULES:
- You ONLY flag conflicts that match the known conflict rule engine.
- You do NOT invent new conflict types. If it's not in the rules, don't flag it.
- You personalize the explanation to mention the specific product names and ingredients.
- Severity levels: "critical" (🔴), "warning" (🟡), "info" (🟢)
"""


def _ingredient_matches_category(ingredient: dict, trigger: dict) -> str | None:
    """
    Check if an ingredient matches a conflict trigger.
    Returns the matched ingredient name or None.
    """
    ing_category = ingredient.get("category", "").lower()
    ing_name = ingredient.get("inci", ingredient.get("name", "")).lower()

    # Check by category match
    if ing_category == trigger["category"].lower():
        return ingredient["name"]

    # Check by specific ingredient name match
    for example in trigger.get("examples", []):
        if example.lower() in ing_name:
            return ingredient["name"]

    return None


def check_product_conflicts(products: list[dict]) -> list[dict]:
    """
    Run N×N conflict analysis across all products.

    This is the core conflict detection engine. For every pair of products,
    it checks every rule in the conflict database.

    Args:
        products: list of product dicts, each with an 'ingredients' list

    Returns:
        list of conflict dicts with product_a, product_b, severity, explanation, fix
    """
    conflicts = []

    for i, product_a in enumerate(products):
        for j, product_b in enumerate(products):
            if j <= i:
                continue  # Don't check a product against itself or duplicate pairs

            for rule in CONFLICT_RULES:
                # Skip rules that need conditions (handled separately)
                if "condition" in rule and "trigger_b" not in rule:
                    continue

                if "trigger_b" not in rule:
                    continue

                # Check if product_a has trigger_a and product_b has trigger_b
                for ing_a in product_a.get("ingredients", []):
                    match_a = _ingredient_matches_category(ing_a, rule["trigger_a"])
                    if not match_a:
                        continue

                    for ing_b in product_b.get("ingredients", []):
                        match_b = _ingredient_matches_category(
                            ing_b, rule["trigger_b"]
                        )
                        if not match_b:
                            continue

                        # Found a conflict!
                        conflicts.append({
                            "rule_id": rule["id"],
                            "type": rule["type"],
                            "severity": rule["severity"],
                            "product_a_id": product_a["id"],
                            "product_a_name": product_a.get("product_name", "Unknown"),
                            "product_b_id": product_b["id"],
                            "product_b_name": product_b.get("product_name", "Unknown"),
                            "ingredient_a": match_a,
                            "ingredient_b": match_b,
                            "explanation": rule["explanation"]
                                .replace("{a}", match_a)
                                .replace("{b}", match_b),
                            "fix": rule["fix"],
                        })

    return conflicts


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