"""
Curl Chemist — Main FastAPI Application

This is the entry point. It serves:
1. The dashboard UI (HTML/CSS/JS)
2. API endpoints the dashboard JavaScript calls
3. Pipeline trigger endpoints (for Cloud Scheduler / Pub/Sub)
"""

import json
import base64
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from typing import Optional

from config import PHOTOS_BUCKET, GCP_PROJECT_ID
from firestore_helpers import (
    get_all_products, get_active_conflicts, get_latest_routine,
    get_recent_pipeline_logs, get_latest_report, get_user_profile,
    get_recent_wash_history, save_product, save_conflict,
    delete_product, clear_all_conflicts, save_wash_entry,
    save_user_profile,
)
from agents.scanner_agent import (
    scan_product_from_bytes, scan_product_by_name,
    scan_product_from_text, scan_product_label,
)
from agents.chemist_agent import check_product_conflicts
from agents.profiler_agent import analyze_hair_photo
from pipelines.nightly_routine import run_nightly_routine_pipeline
from pipelines.shelf_reanalysis import run_shelf_reanalysis_pipeline
from pipelines.weekly_health import run_weekly_health_pipeline

app = FastAPI(title="Curl Chemist", version="1.0.0")

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# HTML templates
templates = Jinja2Templates(directory="dashboard/templates")


# ════════════════════════════════════════════════════
# DASHBOARD — serves the web UI
# ════════════════════════════════════════════════════

@app.get("/")
async def dashboard(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse(request=request, name="index.html")


# ════════════════════════════════════════════════════
# API ENDPOINTS — the dashboard JavaScript calls these
# ════════════════════════════════════════════════════

@app.get("/api/dashboard-data")
async def get_dashboard_data():
    """
    Returns ALL data the dashboard needs in one call.
    The dashboard JavaScript polls this every 5 seconds to stay updated.
    """
    return {
        "products": get_all_products(),
        "conflicts": get_active_conflicts(),
        "routine": get_latest_routine(),
        "profile": get_user_profile(),
        "report": get_latest_report(),
        "pipeline_logs": get_recent_pipeline_logs(limit=20),
        "wash_history": get_recent_wash_history(days=30),
    }


@app.get("/api/products")
async def api_products():
    return get_all_products()


@app.get("/api/conflicts")
async def api_conflicts():
    return get_active_conflicts()


@app.get("/api/routine")
async def api_routine():
    return get_latest_routine() or {}


@app.get("/api/logs")
async def api_logs():
    return get_recent_pipeline_logs()


# ════════════════════════════════════════════════════
# PRODUCT SCANNING — 3 input methods
# All return extracted data for user review BEFORE saving
# ════════════════════════════════════════════════════

@app.post("/api/scan/photo")
async def scan_photo(file: UploadFile = File(...)):
    """
    Scan a product label from an uploaded photo.
    Returns extracted ingredients for user review — does NOT save yet.
    """
    try:
        content = await file.read()
        mime_type = file.content_type or "image/jpeg"
        result = await scan_product_from_bytes(content, mime_type)
        result["scan_method"] = "photo"
        return result
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to scan photo: {str(e)}"},
            status_code=500,
        )


@app.post("/api/scan/name")
async def scan_name(request: Request):
    """
    Look up a product's ingredients by name.
    Gemini recalls the ingredients from its training data.
    Returns extracted ingredients for user review — does NOT save yet.
    """
    try:
        body = await request.json()
        product_name = body.get("product_name", "").strip()
        if not product_name:
            return JSONResponse(
                {"status": "error", "message": "Product name is required"},
                status_code=400,
            )
        result = await scan_product_by_name(product_name)
        return result
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to look up product: {str(e)}"},
            status_code=500,
        )


@app.post("/api/scan/manual")
async def scan_manual(request: Request):
    """
    Parse a manually entered ingredient list.
    The user types/pastes the ingredients themselves.
    Returns structured data for user review — does NOT save yet.
    """
    try:
        body = await request.json()
        product_name = body.get("product_name", "").strip()
        ingredients_text = body.get("ingredients_text", "").strip()

        if not product_name:
            return JSONResponse(
                {"status": "error", "message": "Product name is required"},
                status_code=400,
            )
        if not ingredients_text:
            return JSONResponse(
                {"status": "error", "message": "Ingredients text is required"},
                status_code=400,
            )

        result = await scan_product_from_text(product_name, ingredients_text)
        return result
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to parse ingredients: {str(e)}"},
            status_code=500,
        )


# ════════════════════════════════════════════════════
# CONFIRM & SAVE — user reviews then confirms
# ════════════════════════════════════════════════════

@app.post("/api/confirm-product")
async def confirm_product(request: Request):
    """
    Save a scanned product to the shelf after user review.

    The user has already seen the extracted ingredients from one of the
    /api/scan/* endpoints. Now they confirm it's correct and we:
    1. Save the product to Firestore
    2. Run N×N conflict analysis against the entire shelf
    3. Return any new conflicts found
    """
    try:
        product_data = await request.json()

        # Save to shelf
        product_id = save_product(product_data)
        product_data["id"] = product_id

        # Run conflict analysis against entire shelf
        all_products = get_all_products()
        conflicts = check_product_conflicts(all_products)

        # Filter to only conflicts involving the new product
        new_conflicts = [
            c for c in conflicts
            if c["product_a_id"] == product_id or c["product_b_id"] == product_id
        ]

        # Save new conflicts
        critical_count = 0
        for conflict in new_conflicts:
            save_conflict(conflict)
            if conflict["severity"] == "critical":
                critical_count += 1

        return {
            "status": "success",
            "product_id": product_id,
            "product_name": product_data.get("product_name", "Unknown"),
            "conflicts_found": len(new_conflicts),
            "critical_conflicts": critical_count,
            "conflicts": new_conflicts,
        }

    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to save product: {str(e)}"},
            status_code=500,
        )


# ════════════════════════════════════════════════════
# PRODUCT MANAGEMENT
# ════════════════════════════════════════════════════

@app.delete("/api/products/{product_id}")
async def remove_product(product_id: str):
    """
    Delete a product from the shelf.
    Also removes all conflicts that involved this product.
    """
    try:
        delete_product(product_id)
        return {"status": "success", "message": "Product removed from shelf"}
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to delete product: {str(e)}"},
            status_code=500,
        )


# ════════════════════════════════════════════════════
# WASH DAY SELFIE — feeds the weekly health pipeline
# ════════════════════════════════════════════════════

@app.post("/api/wash-day")
async def log_wash_day(file: UploadFile = File(...), notes: str = Form("")):
    """
    Log a wash day with a hair selfie.

    The profiler agent analyzes the photo, then we save the entry
    with the analysis scores + today's weather + products used.
    This data feeds the weekly health pipeline.
    """
    try:
        from agents.climate_agent import fetch_cairo_weather
        from datetime import datetime, timezone

        # Read the uploaded selfie
        content = await file.read()
        mime_type = file.content_type or "image/jpeg"

        # Encode as base64 data URI for Gemini (no GCS needed locally)
        b64 = base64.b64encode(content).decode()

        # Analyze with profiler agent using inline data
        from google.genai import types
        from config import GEMINI_MODEL

        from google import genai
        prof_client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT_ID,
            location="europe-west1",
        )

        response = await prof_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=content, mime_type=mime_type),
                types.Part.from_text(
                    "Analyze this hair photo. Score the following on a scale of 1-10: "
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

        import json as json_mod
        analysis = json_mod.loads(response.text)

        # Fetch today's weather for correlation
        weather = await fetch_cairo_weather()

        # Get current products on shelf for correlation
        products = get_all_products()
        product_names = [p.get("product_name", "Unknown") for p in products]

        # Save wash entry
        entry = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "analysis": analysis,
            "weather_that_day": weather,
            "products_used": product_names,
            "notes": notes,
        }
        entry_id = save_wash_entry(entry)

        return {
            "status": "success",
            "entry_id": entry_id,
            "analysis": analysis,
        }

    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to log wash day: {str(e)}"},
            status_code=500,
        )


# ════════════════════════════════════════════════════
# USER PROFILE
# ════════════════════════════════════════════════════

@app.post("/api/profile")
async def update_profile(request: Request):
    """Update the user's hair profile."""
    try:
        profile_data = await request.json()
        save_user_profile(profile_data)
        return {"status": "success", "message": "Profile updated"}
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to update profile: {str(e)}"},
            status_code=500,
        )


@app.get("/api/profile")
async def get_profile():
    """Get the user's hair profile."""
    profile = get_user_profile()
    return profile or {}


# ════════════════════════════════════════════════════
# PIPELINE TRIGGER ENDPOINTS
# Cloud Scheduler and Pub/Sub hit these to start pipelines
# ════════════════════════════════════════════════════

@app.post("/pipelines/nightly")
async def trigger_nightly_pipeline(request: Request):
    """
    Triggered by Cloud Scheduler every day at 9 PM Cairo time.
    Generates tomorrow's routine.
    """
    result = await run_nightly_routine_pipeline()
    return JSONResponse(result)


@app.post("/pipelines/shelf-reanalysis")
async def trigger_shelf_reanalysis(request: Request):
    """
    Triggered by Cloud Storage → Pub/Sub when a product photo is uploaded.

    Pub/Sub sends the message as a JSON body with the file details.
    We extract the bucket and filename to build the Cloud Storage URI.
    """
    body = await request.json()

    # Pub/Sub wraps the message in an envelope
    if "message" in body:
        # Decode the Pub/Sub message data
        message_data = body["message"].get("data", "")
        if message_data:
            decoded = json.loads(base64.b64decode(message_data).decode())
            bucket = decoded.get("bucket", PHOTOS_BUCKET)
            name = decoded.get("name", "")
        else:
            return JSONResponse({"status": "error", "message": "No data in Pub/Sub message"}, status_code=400)
    else:
        # Direct API call (for testing)
        bucket = body.get("bucket", PHOTOS_BUCKET)
        name = body.get("name", "")

    if not name:
        return JSONResponse({"status": "error", "message": "No filename provided"}, status_code=400)

    image_uri = f"gs://{bucket}/{name}"
    result = await run_shelf_reanalysis_pipeline(image_uri, name)
    return JSONResponse(result)


@app.post("/pipelines/weekly-health")
async def trigger_weekly_health(request: Request):
    """
    Triggered by Cloud Scheduler every Sunday at 8 PM.
    Analyzes weekly hair health trends.
    """
    result = await run_weekly_health_pipeline()
    return JSONResponse(result)


# ════════════════════════════════════════════════════
# HEALTH CHECK — Cloud Run uses this to know the app is alive
# ════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "curl-chemist"}