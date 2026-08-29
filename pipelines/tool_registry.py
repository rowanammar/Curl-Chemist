"""
Tool Registry — Callable tools for the TaskmasterOrchestrator.

WHY THIS FILE EXISTS:
The GenAI SDK's `tools=` parameter needs Python functions with clear
docstrings and type hints. This module wraps existing business logic
into tool-ready functions the LLM can autonomously discover and call.

Each function here is a self-contained operation the agent can invoke.
The LLM reads the docstring to understand WHAT the tool does and
WHEN to call it, then decides the execution order autonomously.
"""

import json
from datetime import datetime, timedelta, timezone

from agents.scanner_agent import scan_product_label
from agents.chemist_agent import check_product_conflicts, check_climate_conflicts
from agents.climate_agent import fetch_weather, generate_routine
from firestore_helpers import (
    save_product, get_all_products, save_conflict,
    get_active_conflicts, get_user_profile, get_user_location,
    save_routine, log_pipeline_event,
)


# ══════════════════════════════════════════════
# SHELF TOOLS — used by the Shelf Reanalysis agent
# ══════════════════════════════════════════════

async def scan_label(image_uri: str) -> dict:
    """Scan a product label photo and extract structured ingredient data.

    Use this tool when you have a product photo URI and need to extract
    the product name, brand, type, and full ingredient list with
    INCI classifications. Handles Arabic, English, and mixed text.

    Args:
        image_uri: Google Cloud Storage URI (gs://bucket/path/to/photo.jpg)

    Returns:
        dict with product_name, brand, product_type, is_hair_product,
        confidence score, and ingredients array.
    """
    return await scan_product_label(image_uri)


def get_shelf(user_id: str) -> list:
    """Retrieve all products currently on the user's shelf.

    Use this tool to get the full list of products the user has scanned
    and saved, including their ingredients. Needed before running
    conflict analysis.

    Args:
        user_id: The user's unique identifier

    Returns:
        List of product dicts, each with id, product_name, brand,
        product_type, and ingredients array.
    """
    return get_all_products(user_id)


def save_product_to_shelf(user_id: str, product_data_json: str) -> dict:
    """Save a scanned product to the user's shelf in Firestore.

    Use this tool AFTER scanning a label to persist the product.
    The product_data should contain product_name, brand, product_type,
    and ingredients from the scan_label result.

    Args:
        user_id: The user's unique identifier
        product_data_json: JSON string of the product data to save

    Returns:
        dict with the saved product_id and product_name.
    """
    product_data = json.loads(product_data_json) if isinstance(product_data_json, str) else product_data_json
    product_id = save_product(user_id, product_data)
    return {"product_id": product_id, "product_name": product_data.get("product_name", "Unknown")}


async def analyze_conflicts(user_id: str) -> list:
    """Run N×N conflict analysis across ALL products on the user's shelf.

    Use this tool after adding a new product to detect ingredient
    conflicts between products. Checks for silicone buildup,
    protein overload, pH incompatibility, etc.

    Args:
        user_id: The user's unique identifier

    Returns:
        List of conflict dicts, each with product_a_id, product_b_id,
        severity (critical/warning/info), explanation, and fix.
    """
    products = get_all_products(user_id)
    if not products:
        return []
    return await check_product_conflicts(products)


def save_conflict_to_db(user_id: str, conflict_json: str) -> dict:
    """Save a detected conflict to Firestore.

    Use this tool for each conflict found by analyze_conflicts.
    Persists the conflict so it appears in the user's dashboard.

    Args:
        user_id: The user's unique identifier
        conflict_json: JSON string of the conflict data

    Returns:
        dict with the saved conflict_id.
    """
    conflict = json.loads(conflict_json) if isinstance(conflict_json, str) else conflict_json
    conflict_id = save_conflict(user_id, conflict)
    return {"conflict_id": conflict_id, "severity": conflict.get("severity", "unknown")}


def get_active_shelf_conflicts(user_id: str) -> list:
    """Get all currently unresolved conflicts on the user's shelf.

    Use this to check what conflicts already exist before adding new ones.

    Args:
        user_id: The user's unique identifier

    Returns:
        List of active conflict dicts.
    """
    return get_active_conflicts(user_id)


# ══════════════════════════════════════════════
# NIGHTLY ROUTINE TOOLS — used by the Nightly Routine agent
# ══════════════════════════════════════════════

async def fetch_weather_forecast(user_id: str) -> dict:
    """Fetch tomorrow's weather forecast for the user's location.

    Use this tool to get humidity, UV index, temperature, dew point,
    and precipitation data. Essential for climate-aware routine generation.

    Args:
        user_id: The user's unique identifier

    Returns:
        dict with temperature_max, temperature_min, humidity, uv_index,
        dew_point, wind_speed, precipitation_probability.
    """
    location = get_user_location(user_id)
    weather = await fetch_weather(location["latitude"], location["longitude"])
    weather["city"] = location.get("city", "Unknown")
    return weather


def get_user_hair_profile(user_id: str) -> dict:
    """Retrieve the user's hair profile (type, porosity, goals, etc.).

    Use this tool to personalize routines and recommendations
    to the user's specific hair characteristics.

    Args:
        user_id: The user's unique identifier

    Returns:
        dict with hair_type, porosity, protein_sensitivity, thickness,
        goals, and adaptive_profile (learned preferences).
    """
    profile = get_user_profile(user_id)
    if not profile:
        return {
            "hair_type": "2B wavy",
            "porosity": "medium",
            "goals": ["reduce frizz", "improve definition"],
        }
    return profile


def detect_climate_conflicts(products_json: str, humidity: float, uv_index: float) -> list:
    """Check for weather-dependent ingredient conflicts.

    Use this tool AFTER fetching weather to identify products that
    should be avoided under current climate conditions (e.g., glycerin
    in high humidity, lack of UV protection on high UV days).

    Args:
        products_json: JSON string of the user's product shelf
        humidity: Tomorrow's humidity percentage
        uv_index: Tomorrow's UV index

    Returns:
        List of climate conflict dicts with product_name, ingredient,
        condition, explanation, and fix.
    """
    products = json.loads(products_json) if isinstance(products_json, str) else products_json
    return check_climate_conflicts(products, humidity, uv_index)


async def generate_hair_routine(
    products_json: str,
    weather_json: str,
    profile_json: str,
    climate_conflicts_json: str = "[]",
) -> dict:
    """Generate a personalized daily hair care routine.

    Use this tool after gathering weather, products, profile, and
    climate conflicts. Produces a step-by-step routine using only
    products from the user's shelf.

    Args:
        products_json: JSON string of available products
        weather_json: JSON string of tomorrow's weather
        profile_json: JSON string of user's hair profile
        climate_conflicts_json: JSON string of climate conflicts to avoid

    Returns:
        dict with summary, is_wash_day, steps array, and climate_notes.
    """
    products = json.loads(products_json) if isinstance(products_json, str) else products_json
    weather = json.loads(weather_json) if isinstance(weather_json, str) else weather_json
    profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
    climate_conflicts = json.loads(climate_conflicts_json) if isinstance(climate_conflicts_json, str) else climate_conflicts_json
    return await generate_routine(products, weather, profile, climate_conflicts=climate_conflicts)


def save_routine_to_db(user_id: str, date_str: str, routine_data_json: str) -> dict:
    """Save a generated routine for a specific date to Firestore.

    Use this tool to persist the routine after generation.
    Uses the date as document ID so re-runs are idempotent.

    Args:
        user_id: The user's unique identifier
        date_str: Date string in YYYY-MM-DD format
        routine_data_json: JSON string of the full routine data

    Returns:
        dict confirming the save with the date.
    """
    routine_data = json.loads(routine_data_json) if isinstance(routine_data_json, str) else routine_data_json
    save_routine(user_id, date_str, routine_data)
    return {"status": "saved", "date": date_str}


# ══════════════════════════════════════════════
# TOOL COLLECTIONS — grouped by pipeline
# ══════════════════════════════════════════════

# Import external actions (FIX 2)
from pipelines.external_actions import schedule_calendar_event, dispatch_shopping_alert

SHELF_REANALYSIS_TOOLS = [
    scan_label,
    get_shelf,
    save_product_to_shelf,
    analyze_conflicts,
    save_conflict_to_db,
    get_active_shelf_conflicts,
    dispatch_shopping_alert,
]

NIGHTLY_ROUTINE_TOOLS = [
    get_shelf,
    fetch_weather_forecast,
    get_user_hair_profile,
    detect_climate_conflicts,
    generate_hair_routine,
    save_routine_to_db,
    save_conflict_to_db,
    schedule_calendar_event,
]
