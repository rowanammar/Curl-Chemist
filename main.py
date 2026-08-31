"""
Curl Chemist — Main FastAPI Application

This is the entry point. It serves:
1. The dashboard UI (HTML/CSS/JS)
2. API endpoints the dashboard JavaScript calls
3. Pipeline trigger endpoints (for Cloud Scheduler / Pub/Sub)
"""

import json
import base64
from datetime import datetime, timezone
from fastapi import FastAPI, Request, UploadFile, File, Form, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from typing import Optional

from config import PHOTOS_BUCKET, GCP_PROJECT_ID, GEOCODING_API_URL
from auth import hash_password, verify_password, create_access_token, decode_access_token
from firestore_helpers import (
    db, get_all_products, get_active_conflicts, get_latest_routine,
    get_recent_pipeline_logs, get_latest_report, get_user_profile,
    get_recent_wash_history, save_product, save_conflict,
    delete_product, clear_all_conflicts, save_wash_entry,
    save_user_profile, log_pipeline_event,
    # New user management functions
    username_exists, create_user, get_user_by_username,
    upload_photo_to_gcs, upload_profile_photo_to_gcs,
    get_all_wash_history, get_user_location,
    get_recent_alerts, get_recent_calendar_events,
)
from agents.scanner_agent import (
    scan_product_from_bytes, scan_product_by_name,
    scan_product_from_text, scan_product_label,
)
from agents.chemist_agent import check_product_conflicts
from agents.profiler_agent import analyze_hair_photo
from agents.wash_comparison_agent import compare_wash_days_with_photos
from agents.advisor_agent import generate_advisor_response
from pipelines.nightly_routine import run_nightly_routine_pipeline
from pipelines.shelf_reanalysis import run_shelf_check_pipeline
from pipelines.weekly_health import run_weekly_health_pipeline

app = FastAPI(title="Curl Chemist", version="2.0.0")

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# HTML templates
templates = Jinja2Templates(directory="dashboard/templates")


# ════════════════════════════════════════════════════
# AGENT GATEWAY MIDDLEWARE
# ════════════════════════════════════════════════════
from fastapi.responses import JSONResponse

@app.middleware("http")
async def agent_gateway_middleware(request: Request, call_next):
    """
    Agent Gateway: Unified routing and policy enforcement.
    Provides Zero-Trust access control to agentic pipelines.
    """
    path = request.url.path
    
    # Allow public endpoints (Dashboard, Auth, static files)
    if path == "/" or path.startswith("/static") or path.startswith("/api/auth") or path == "/favicon.ico":
        return await call_next(request)
        
    # Check internal Cloud Scheduler / PubSub OIDC Tokens for pipeline triggers
    if path.startswith("/pipelines/") or path.startswith("/pubsub/"):
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                from google.oauth2 import id_token
                from google.auth.transport import requests
                request_transport = requests.Request()
                id_info = id_token.verify_oauth2_token(token, request_transport)
                request.state.is_internal = True
                return await call_next(request)
            except Exception as e:
                if path.startswith("/pubsub/"):
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=401,
                        content={"status": "error", "message": f"Agent Gateway: OIDC Authentication failed - {str(e)}"}
                    )
                pass # Fall through to JWT check if not a valid Google OIDC token
        elif path.startswith("/pubsub/"):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Agent Gateway: Missing OIDC Token for /pubsub/"}
            )

    # Check JWT Token
    if path.startswith("/api/") or path.startswith("/pipelines/"):
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Agent Gateway: Zero-Trust Policy Violation"}
            )
        token = auth_header.split(" ")[1]
        try:
            payload = decode_access_token(token)
            request.state.user_id = payload.get("sub")
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": f"Agent Gateway: Authentication failed - {str(e)}"}
            )
            
    return await call_next(request)


# ════════════════════════════════════════════════════
# HELPER — extract user_id from request headers
# ════════════════════════════════════════════════════

def get_user_id(request: Request) -> str:
    """Agent Gateway: Enforces Zero-Trust Access Control."""
    user_id = getattr(request.state, "user_id", "")
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Agent Gateway: Missing User ID for Zero-Trust routing.")
    return user_id


# ════════════════════════════════════════════════════
# DASHBOARD — serves the web UI
# ════════════════════════════════════════════════════

@app.get("/")
async def dashboard(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse(request=request, name="index.html")


# ════════════════════════════════════════════════════
# AUTH ENDPOINTS — Signup / Login / Username Check
# ════════════════════════════════════════════════════

@app.get("/api/auth/check-username/{username}")
async def check_username(username: str):
    """Check if a username is available."""
    username = username.strip().lower()
    if len(username) < 2:
        return {"available": False, "reason": "Username must be at least 2 characters"}
    if len(username) > 30:
        return {"available": False, "reason": "Username must be 30 characters or less"}
    if not username.replace("_", "").replace("-", "").isalnum():
        return {"available": False, "reason": "Username can only contain letters, numbers, hyphens, and underscores"}

    exists = username_exists(username)
    return {
        "available": not exists,
        "reason": "Username is already taken" if exists else "Username is available",
    }
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

@app.post("/api/auth/signup")
async def signup(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    hair_type: str = Form(""),
    porosity: str = Form(""),
    protein_sensitivity: str = Form(""),
    thickness: str = Form(""),
    color_history: str = Form(""),
    goals: str = Form(""),
    city: str = Form(""),
    latitude: float = Form(0),
    longitude: float = Form(0),
    timezone: str = Form("UTC"),
    photo: Optional[UploadFile] = File(None),
):
    """
    Create a new user account with hair profile and location.
    """
    try:
        username = username.strip().lower()

        # Validate username
        if len(username) < 2:
            return JSONResponse(
                {"status": "error", "message": "Username must be at least 2 characters"},
                status_code=400,
            )
            
        # Validate email
        email = email.strip()
        if not email or "@" not in email:
            return JSONResponse(
                {"status": "error", "message": "A valid email address is required"},
                status_code=400,
            )

        # Parse goals from comma-separated string
        goals_list = [g.strip() for g in goals.split(",") if g.strip()] if goals else []

        # Hair profile
        hair_profile = {
            "hair_type": hair_type,
            "porosity": porosity,
            "protein_sensitivity": protein_sensitivity,
            "thickness": thickness,
            "color_history": color_history,
            "goals": goals_list,
        }

        # Location
        location = {
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
        }

        # Upload optional profile photo to GCS
        photo_url = None
        if photo and photo.filename:
            photo_bytes = await photo.read()
            mime_type = photo.content_type or "image/jpeg"
            photo_url = upload_profile_photo_to_gcs(username, photo_bytes, mime_type)

            # Also analyze the initial photo with Gemini
            try:
                from google.genai import types
                from google import genai
                from config import GEMINI_MODEL, GCP_REGION, GCP_PROJECT_ID

                prof_client = genai.Client(
                    vertexai=True,
                    project=GCP_PROJECT_ID,
                    location=GCP_REGION,
                )

                response = await prof_client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[
                        types.Part.from_bytes(data=photo_bytes, mime_type=mime_type),
                        types.Part.from_text(
                            text="Analyze this hair photo. Determine the hair type (1A-4C), "
                            "porosity indicators, thickness, and condition. "
                            "Return JSON with keys: suggested_hair_type, suggested_porosity, "
                            "suggested_thickness, observations."
                        ),
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                )

                import json as json_mod
                photo_analysis = json_mod.loads(response.text)
                hair_profile["photo_analysis"] = photo_analysis
            except Exception:
                pass  # Photo analysis is optional — don't block signup

        # Create the user
        user_data = create_user(username, email, hash_password(password), hair_profile, location, photo_url)

        # Trigger welcome email (this will trigger Google Auth popup locally the first time)
        try:
            import asyncio
            from google_api_service import send_welcome_email
            asyncio.create_task(asyncio.to_thread(send_welcome_email, email, username))
        except Exception as e:
            print(f"Error triggering welcome email: {e}")

        token = create_access_token(username)

        return {
            "status": "success",
            "username": username,
            "token": token,
            "message": f"Welcome to Curl Chemist, {username}!",
            "photo_analysis": hair_profile.get("photo_analysis"),
        }

    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Signup failed: {str(e)}"}


@app.post("/api/auth/login")
async def login(request: Request):
    """Login by username."""
    try:
        body = await request.json()
        username = body.get("username", "").strip().lower()

        if not username:
            return {"status": "error", "message": "Username is required"}

        password = body.get("password", "")
        if not password:
            return {"status": "error", "message": "Password is required"}

        user = get_user_by_username(username)
        if not user:
            return {"status": "error", "message": "User doesn't exist."}
        if not user.get("password_hash") or not verify_password(password, user.get("password_hash")):
            return {"status": "error", "message": "Incorrect password."}

        token = create_access_token(username)

        return {
            "status": "success",
            "username": username,
            "token": token,
            "user": user,
        }

    except Exception as e:
        return {"status": "error", "message": f"Login failed: {str(e)}"}


@app.get("/api/auth/geocode")
async def geocode_city(city: str):
    """Geocode a city name to lat/lon using Open-Meteo's free geocoding API."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(GEOCODING_API_URL, params={
                "name": city,
                "count": 5,
                "language": "en",
                "format": "json",
            })
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        return {
            "results": [
                {
                    "name": r.get("name", ""),
                    "country": r.get("country", ""),
                    "admin1": r.get("admin1", ""),  # State/province
                    "latitude": r.get("latitude"),
                    "longitude": r.get("longitude"),
                    "timezone": r.get("timezone", "UTC"),
                }
                for r in results
            ]
        }
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Geocoding failed: {str(e)}"},
            status_code=500,
        )


# ════════════════════════════════════════════════════
# API ENDPOINTS — the dashboard JavaScript calls these
# All endpoints require X-User-Id header
# ════════════════════════════════════════════════════

@app.get("/api/dashboard-data")
async def get_dashboard_data(request: Request):
    """
    Returns ALL data the dashboard needs in one call.
    The dashboard JavaScript polls this every 5 seconds to stay updated.
    """
    user_id = get_user_id(request)
    if not user_id:
        return {"products": [], "conflicts": [], "routine": None, "profile": None,
                "report": None, "pipeline_logs": [], "wash_history": [],
                "alerts": [], "calendar_events": []}

    logs = get_recent_pipeline_logs(user_id, limit=100)
    
    is_analyzing = False
    for log in logs:
        if log.get("pipeline") == "shelf_check":
            if log.get("status") == "info":
                is_analyzing = True
            break

    return {
        "products": get_all_products(user_id),
        "conflicts": get_active_conflicts(user_id),
        "routine": get_latest_routine(user_id),
        "profile": get_user_profile(user_id),
        "report": get_latest_report(user_id),
        "pipeline_logs": logs,
        "wash_history": get_recent_wash_history(user_id, days=30),
        "alerts": get_recent_alerts(user_id),
        "calendar_events": get_recent_calendar_events(user_id),
        "is_analyzing": is_analyzing,
    }




@app.get("/api/conflicts")
async def api_conflicts(request: Request):
    user_id = get_user_id(request)
    return get_active_conflicts(user_id)


@app.get("/api/routine")
async def api_routine(request: Request):
    user_id = get_user_id(request)
    return get_latest_routine(user_id) or {}


@app.get("/api/logs")
async def api_logs(request: Request):
    user_id = get_user_id(request)
    return get_recent_pipeline_logs(user_id)


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: Request):
    user_id = get_user_id(request)
    if not user_id:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)
    
    from firestore_helpers import get_user_ref
    try:
        get_user_ref(user_id).collection("alerts").document(alert_id).update({"acknowledged": True})
        return {"status": "success"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


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
    user_id = get_user_id(request)
    if not user_id:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)

    try:
        product_data = await request.json()

        # Save to shelf
        product_id = save_product(user_id, product_data)
        product_data["id"] = product_id
        product_name = product_data.get("product_name", "Unknown")
        log_pipeline_event(user_id, "system", f"Added product to shelf: {product_name}")

        # Trigger Autonomous Agent in the background to handle Conflicts and Alerts
        import asyncio
        asyncio.create_task(run_shelf_check_pipeline(user_id))

        return {
            "status": "success",
            "product_id": product_id,
            "product_name": product_name,
            "conflicts_found": 0,
            "critical_conflicts": 0,
            "conflicts": [],
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
async def remove_product(product_id: str, request: Request):
    """
    Delete a product from the shelf.
    Re-evaluates conflicts for the remaining shelf.
    """
    user_id = get_user_id(request)
    if not user_id:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)

    try:
        delete_product(user_id, product_id)
        log_pipeline_event(user_id, "system", "Removed a product from the shelf")

        # Trigger Autonomous Agent in the background to handle Conflicts and Alerts
        import asyncio
        asyncio.create_task(run_shelf_check_pipeline(user_id))

        return {"status": "success", "message": "Product removed and shelf re-evaluation started"}
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to delete product: {str(e)}"},
            status_code=500,
        )


# ════════════════════════════════════════════════════
# WASH DAY SELFIE — feeds the weekly health pipeline
# Now stores photos in GCS and runs comparative analysis
# ════════════════════════════════════════════════════

@app.post("/api/wash-day")
async def log_wash_day(
    request: Request,
    file: UploadFile = File(...),
    notes: str = Form(""),
):
    """
    Log a wash day with a hair selfie.

    The profiler agent analyzes the photo, then we:
    1. Upload photo to GCS bucket
    2. Analyze with Gemini Vision
    3. Fetch today's weather for the user's location
    4. Compare with previous wash days (photo + metrics + climate)
    5. Save everything and return insights
    """
    user_id = get_user_id(request)
    if not user_id:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)

    try:
        from agents.climate_agent import fetch_weather
        from google.genai import types
        from google import genai
        from config import GEMINI_MODEL, GCP_REGION, GEMINI_API_KEY

        # Read the uploaded selfie
        content = await file.read()
        mime_type = file.content_type or "image/jpeg"

        # Step 1: Upload photo to GCS
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"wash_{timestamp}.jpg"
        photo_url = upload_photo_to_gcs(user_id, content, filename, mime_type)

        # Step 2: Analyze with profiler agent using inline data
        prof_client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT_ID,
            location=GCP_REGION,
        )

        response = await prof_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=content, mime_type=mime_type),
                types.Part.from_text(
                    text="Analyze this hair photo. Score the following on a scale of 1-10: "
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

        # Step 3: Fetch today's weather for the USER'S location
        location = get_user_location(user_id)
        weather = await fetch_weather(location["latitude"], location["longitude"])

        # Step 4: Get current products on shelf for correlation
        products = get_all_products(user_id)
        product_names = [p.get("product_name", "Unknown") for p in products]

        # Step 5: Build the wash entry
        entry = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "analysis": analysis,
            "weather_that_day": weather,
            "products_used": product_names,
            "notes": notes,
            "photo_url": photo_url,  # GCS URI for photo comparison
        }

        # Step 6: Run comparative analysis against previous wash days
        previous_entries = get_all_wash_history(user_id, limit=10)
        user_profile = get_user_profile(user_id)

        comparison = None
        try:
            comparison = await compare_wash_days_with_photos(
                current_photo_uri=photo_url,
                current_entry=entry,
                previous_entries_with_photos=previous_entries,
                user_profile=user_profile,
            )
            entry["comparison"] = comparison
        except Exception as comp_err:
            # Comparison is bonus — don't fail the entire wash day log
            entry["comparison_error"] = str(comp_err)

        # Step 7: Save wash entry
        entry_id = save_wash_entry(user_id, entry)
        log_pipeline_event(user_id, "system", "Wash day logged, analyzed, and compared")

        return {
            "status": "success",
            "entry_id": entry_id,
            "analysis": analysis,
            "comparison": comparison,
            "photo_url": photo_url,
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
    user_id = get_user_id(request)
    if not user_id:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)

    try:
        profile_data = await request.json()
        save_user_profile(user_id, profile_data)
        return {"status": "success", "message": "Profile updated"}
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to update profile: {str(e)}"},
            status_code=500,
        )


@app.get("/api/profile")
async def get_profile(request: Request):
    """Get the user's hair profile."""
    user_id = get_user_id(request)
    if not user_id:
        return {}
    profile = get_user_profile(user_id)
    return profile or {}


# ════════════════════════════════════════════════════
# WASH HISTORY — for the progress gallery
# ════════════════════════════════════════════════════

@app.get("/api/wash-history")
async def api_wash_history(
    request: Request,
    days: int = 90,
):
    """Get wash history entries for the timeline/gallery."""
    user_id = get_user_id(request)
    if not user_id:
        return []
    return get_recent_wash_history(user_id, days=days)


# ════════════════════════════════════════════════════
# PIPELINE TRIGGER ENDPOINTS
# Cloud Scheduler and Pub/Sub hit these to start pipelines
# ════════════════════════════════════════════════════

@app.post("/pipelines/nightly")
async def trigger_nightly_pipeline(
    request: Request,
):
    """
    Triggered manually by a user from the dashboard.
    Generates tomorrow's routine.
    """
    user_id = get_user_id(request)
    if not user_id:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)

    result = await run_nightly_routine_pipeline(user_id)
    return JSONResponse(jsonable_encoder(result))

@app.post("/pipelines/nightly/run-all")
async def trigger_nightly_pipeline_all_users(request: Request):
    """
    Triggered by Cloud Scheduler every day at 9 PM Cairo time.
    Runs the nightly routine for all users.
    Requires OIDC authentication.
    """
    if not getattr(request.state, "is_internal", False):
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
        
    from firestore_helpers import get_all_users
    users = get_all_users()
    
    import asyncio
    for user in users:
        user_id = user.get("id")
        if user_id:
            asyncio.create_task(run_nightly_routine_pipeline(user_id))
            
    return {"status": "success", "message": f"Triggered nightly routine for {len(users)} users"}





@app.post("/pipelines/weekly-health")
async def trigger_weekly_health(
    request: Request,
):
    """
    Triggered by Cloud Scheduler every Sunday at 8 PM.
    Analyzes weekly hair health trends.
    """
    user_id = get_user_id(request)
    if not user_id:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)

    result = await run_weekly_health_pipeline(user_id)
    return JSONResponse(jsonable_encoder(result))


# ════════════════════════════════════════════════════
# ADVISOR CHAT
# ════════════════════════════════════════════════════

@app.post("/api/advisor/chat")
async def advisor_chat(
    request: Request,
):
    """Handles chat messages to the Curl Advisor."""
    user_id = get_user_id(request)
    if not user_id:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)

    try:
        body = await request.json()
        message = body.get("message", "")
        chat_history = body.get("history", [])

        if not message:
            return JSONResponse({"status": "error", "message": "Message is required"}, status_code=400)

        # Gather user context
        from firestore_helpers import get_user_location
        profile = get_user_profile(user_id) or {}
        profile["location"] = get_user_location(user_id) or {}
        
        user_context = {
            "profile": profile,
            "products": get_all_products(user_id) or [],
            "wash_history": get_recent_wash_history(user_id, days=30) or [],
            "routine": get_latest_routine(user_id) or {},
        }

        # Generate response
        reply = await generate_advisor_response(
            user_id=user_id,
            user_context=user_context,
            chat_history=chat_history,
            user_message=message
        )

        return {"status": "success", "reply": reply}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ════════════════════════════════════════════════════
# HEALTH CHECK — Cloud Run uses this to know the app is alive
# ════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "curl-chemist", "version": "2.0.0"}

@app.post("/pipelines/nightly/run-all")
async def trigger_nightly_run_all(request: Request):
    """Run nightly routine for all users concurrently."""
    if not getattr(request.state, "is_internal", False):
        return JSONResponse({"status": "error", "message": "Unauthorized. Internal OIDC token required."}, status_code=403)
        
    import asyncio
    users = db.collection("users").stream()
    
    async def process_user(uid):
        try:
            res = await run_nightly_routine_pipeline(uid)
            return {"user": uid, "status": "success", "result": res}
        except Exception as e:
            return {"user": uid, "status": "error", "message": str(e)}
    tasks = [process_user(user_doc.id) for user_doc in users]
    results = await asyncio.gather(*tasks)
    
    return JSONResponse({"status": "completed", "results": results})

@app.post("/pubsub/push")
async def pubsub_push_handler(request: Request):
    """Event-driven intake triggered by Cloud Storage via Pub/Sub."""
    import base64
    import json
    import asyncio
    
    try:
        body = await request.json()
        message = body.get("message", {})
        data_b64 = message.get("data")
        
        if not data_b64:
            return JSONResponse({"status": "error", "message": "No data in Pub/Sub message"}, status_code=400)
            
        # Decode base64 data
        decoded_data = base64.b64decode(data_b64).decode("utf-8")
        event_payload = json.loads(decoded_data)
        
        # Example: GCS Object create event payload contains 'name' (e.g., 'user123/wash_photos/image.jpg')
        file_path = event_payload.get("name", "")
        if not file_path:
            return {"status": "ignored", "message": "No file path in event"}
            
        # Extract user_id from the GCS file path structure
        user_id = file_path.split("/")[0]
        
        # Trigger the background autonomous agent workflow
        asyncio.create_task(run_shelf_check_pipeline(user_id))
        
        return {"status": "success", "message": f"Triggered pipeline for {user_id}"}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
