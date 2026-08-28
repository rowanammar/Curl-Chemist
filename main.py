import json
import base64
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from google.cloud import storage

from config import PHOTOS_BUCKET, GCP_PROJECT_ID
from firestore_helpers import (
    get_all_products, get_active_conflicts, get_latest_routine,
    get_recent_pipeline_logs, get_latest_report, get_user_profile,
    get_recent_wash_history,
)
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
    return templates.TemplateResponse("index.html", {"request": request})


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
# MANUAL UPLOAD — for the dashboard "Scan New Product" button
# ════════════════════════════════════════════════════

@app.post("/api/upload-product")
async def upload_product_photo(file: UploadFile = File(...)):
    """
    Upload a product photo directly from the dashboard.
    This uploads to Cloud Storage, which triggers Pipeline 2 automatically
    via the Cloud Storage → Pub/Sub notification we set up.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(PHOTOS_BUCKET)

    # Upload to Cloud Storage
    blob_name = f"products/{file.filename}"
    blob = bucket.blob(blob_name)
    content = await file.read()
    blob.upload_from_string(content, content_type=file.content_type)

    return {
        "status": "uploaded",
        "message": f"Photo uploaded — shelf reanalysis cascade will trigger automatically",
        "uri": f"gs://{PHOTOS_BUCKET}/{blob_name}",
    }


# ════════════════════════════════════════════════════
# HEALTH CHECK — Cloud Run uses this to know the app is alive
# ════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "curl-chemist"}