from google.cloud import firestore
from google.cloud import storage
from datetime import datetime, timezone
from config import PHOTOS_BUCKET

# Initialize clients once, reuse everywhere
db = firestore.Client()
gcs_client = storage.Client()
bucket = gcs_client.bucket(PHOTOS_BUCKET)


# ══════════════════════════════════════════════
# User Reference — ALL data is scoped per user
# ══════════════════════════════════════════════

def get_user_ref(user_id: str):
    """Get a reference to a user's document."""
    return db.collection("users").document(user_id)


# ══════════════════════════════════════════════
# User Management — Signup / Login / Validation
# ══════════════════════════════════════════════

def username_exists(username: str) -> bool:
    """Check if a username is already taken."""
    doc = db.collection("users").document(username).get()
    return doc.exists


def create_user(username: str, email: str, password_hash: str, hair_profile: dict, location: dict, photo_url: str = None) -> dict:
    """
    Create a new user account.

    Args:
        username: unique username (used as document ID)
        email: user's email address
        password_hash: hashed password
        hair_profile: dict with hair_type, porosity, protein_sensitivity, etc.
        location: dict with city, latitude, longitude, timezone
        photo_url: optional GCS URL of initial hair photo

    Returns:
        The created user document data

    Raises:
        ValueError if username already exists
    """
    if username_exists(username):
        raise ValueError(f"Username '{username}' is already taken")

    user_data = {
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "created_at": datetime.now(timezone.utc),
        "location": location,
    }
    user_ref = db.collection("users").document(username)
    user_ref.set(user_data)

    # Save hair profile as a sub-document
    profile_data = {
        **hair_profile,
        "updated_at": datetime.now(timezone.utc),
    }
    if photo_url:
        profile_data["initial_photo_url"] = photo_url
    user_ref.collection("profile").document("hair").set(profile_data)

    return user_data


def get_user_by_username(username: str) -> dict | None:
    """Look up a user by username. Returns user data or None."""
    doc = db.collection("users").document(username).get()
    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


def get_all_users() -> list[dict]:
    """Get a list of all users."""
    docs = db.collection("users").stream()
    users = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        users.append(data)
    return users


# ══════════════════════════════════════════════
# Photo Storage — Upload to GCS bucket
# ══════════════════════════════════════════════

def upload_photo_to_gcs(user_id: str, photo_bytes: bytes, filename: str, content_type: str = "image/jpeg") -> str:
    """
    Upload a photo to GCS and return the public URI.

    Photos are stored under: {user_id}/wash_photos/{filename}
    Returns the gs:// URI.
    """
    blob_path = f"{user_id}/wash_photos/{filename}"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(photo_bytes, content_type=content_type)
    return f"gs://{PHOTOS_BUCKET}/{blob_path}"


def upload_profile_photo_to_gcs(user_id: str, photo_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Upload a profile/initial hair photo to GCS."""
    blob_path = f"{user_id}/profile_photos/initial.jpg"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(photo_bytes, content_type=content_type)
    return f"gs://{PHOTOS_BUCKET}/{blob_path}"


def get_signed_url(gcs_uri: str, expiration_minutes: int = 60) -> str:
    """
    Generate a signed URL for a GCS object so the browser can display it.

    Args:
        gcs_uri: gs://bucket/path format
        expiration_minutes: how long the URL is valid

    Returns:
        A signed HTTPS URL
    """
    import datetime as dt

    # Parse gs:// URI
    path = gcs_uri.replace(f"gs://{PHOTOS_BUCKET}/", "")
    blob = bucket.blob(path)
    url = blob.generate_signed_url(
        expiration=dt.timedelta(minutes=expiration_minutes),
        method="GET",
    )
    return url


# ══════════════════════════════════════════════
# Products — per-user shelf
# ══════════════════════════════════════════════

def save_product(user_id: str, product_data: dict) -> str:
    """
    Save a scanned product to the user's shelf.
    Returns the auto-generated document ID.
    """
    product_data["scanned_at"] = datetime.now(timezone.utc)
    doc_ref = get_user_ref(user_id).collection("products").document()
    doc_ref.set(product_data)
    return doc_ref.id


def get_all_products(user_id: str) -> list[dict]:
    """Get all products on the user's shelf."""
    docs = get_user_ref(user_id).collection("products").stream()
    products = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        products.append(data)
    return products


def delete_product(user_id: str, product_id: str):
    """
    Delete a product from the user's shelf.
    Also clears any conflicts that involved this product.
    """
    get_user_ref(user_id).collection("products").document(product_id).delete()
    clear_conflicts_for_product(user_id, product_id)


def clear_conflicts_for_product(user_id: str, product_id: str):
    """Remove all conflicts that involve a specific product."""
    conflicts_ref = get_user_ref(user_id).collection("conflicts")

    # Check product_a_id
    docs_a = conflicts_ref.where("product_a_id", "==", product_id).stream()
    for doc in docs_a:
        doc.reference.delete()

    # Check product_b_id
    docs_b = conflicts_ref.where("product_b_id", "==", product_id).stream()
    for doc in docs_b:
        doc.reference.delete()

    # Also check single-product conflicts (climate conflicts)
    docs_single = conflicts_ref.where("product_id", "==", product_id).stream()
    for doc in docs_single:
        doc.reference.delete()


def clear_all_conflicts(user_id: str):
    """Clear all conflicts. Used before a full shelf re-analysis."""
    docs = get_user_ref(user_id).collection("conflicts").stream()
    for doc in docs:
        doc.reference.delete()


# ══════════════════════════════════════════════
# Conflicts
# ══════════════════════════════════════════════

import hashlib

def save_conflict(user_id: str, conflict_data: dict) -> str:
    """Save a detected conflict idempotently."""
    conflict_data["detected_at"] = datetime.now(timezone.utc)
    conflict_data["resolved"] = False
    
    # Generate a deterministic ID to prevent duplicates when pipeline runs multiple times
    rule_id = conflict_data.get("rule_id", "unknown")
    prod_a = str(conflict_data.get("product_a_id", ""))
    prod_b = str(conflict_data.get("product_b_id", ""))
    
    hash_input = f"{user_id}_{rule_id}_{prod_a}_{prod_b}"
    conflict_hash = hashlib.md5(hash_input.encode("utf-8")).hexdigest()
    
    doc_ref = get_user_ref(user_id).collection("conflicts").document(conflict_hash)
    doc_ref.set(conflict_data)
    return conflict_hash


def get_active_conflicts(user_id: str) -> list[dict]:
    """Get all unresolved conflicts."""
    docs = (
        get_user_ref(user_id)
        .collection("conflicts")
        .where("resolved", "==", False)
        .stream()
    )
    conflicts = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        conflicts.append(data)
    return conflicts


# ══════════════════════════════════════════════
# Routines
# ══════════════════════════════════════════════

def save_routine(user_id: str, date_str: str, routine_data: dict):
    """
    Save a generated routine for a specific date.
    Uses the date as the document ID → idempotent.
    (If the pipeline runs twice for the same date, it overwrites, not duplicates.)
    """
    routine_data["generated_at"] = datetime.now(timezone.utc)
    routine_data["generated_by"] = "nightly_pipeline"
    get_user_ref(user_id).collection("routines").document(date_str).set(routine_data)


def get_routine(user_id: str, date_str: str) -> dict | None:
    """Get the routine for a specific date."""
    doc = get_user_ref(user_id).collection("routines").document(date_str).get()
    return doc.to_dict() if doc.exists else None


def get_latest_routine(user_id: str) -> dict | None:
    """Get the most recently generated routine."""
    docs = (
        get_user_ref(user_id)
        .collection("routines")
        .order_by("generated_at", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


# ══════════════════════════════════════════════
# Wash History
# ══════════════════════════════════════════════

def save_wash_entry(user_id: str, entry_data: dict) -> str:
    """Save a wash day entry with photo analysis."""
    entry_data["created_at"] = datetime.now(timezone.utc)
    doc_ref = get_user_ref(user_id).collection("wash_history").document()
    doc_ref.set(entry_data)
    return doc_ref.id


def get_recent_wash_history(user_id: str, days: int = 7) -> list[dict]:
    """Get wash history entries from the last N days."""
    cutoff = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0
    )
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)

    docs = (
        get_user_ref(user_id)
        .collection("wash_history")
        .where("created_at", ">=", cutoff)
        .order_by("created_at")
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


def get_all_wash_history(user_id: str, limit: int = 20) -> list[dict]:
    """Get all wash history entries (for comparative analysis)."""
    docs = (
        get_user_ref(user_id)
        .collection("wash_history")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


# ══════════════════════════════════════════════
# Reports
# ══════════════════════════════════════════════

def save_weekly_report(user_id: str, week_str: str, report_data: dict):
    """Save a weekly health report. Idempotent by week string."""
    report_data["generated_at"] = datetime.now(timezone.utc)
    report_data["generated_by"] = "weekly_pipeline"
    get_user_ref(user_id).collection("reports").document(f"weekly_{week_str}").set(
        report_data
    )


def get_latest_report(user_id: str) -> dict | None:
    """Get the most recent weekly report."""
    docs = (
        get_user_ref(user_id)
        .collection("reports")
        .order_by("generated_at", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


# ══════════════════════════════════════════════
# Pipeline Logs
# ══════════════════════════════════════════════
import os
import json

try:
    from google.cloud import dlp_v2
    dlp_client = dlp_v2.DlpServiceClient()
except ImportError:
    dlp_client = None

def redact_pii(text: str) -> str:
    """Uses Google Cloud DLP to redact sensitive PII (like email addresses) from logs."""
    from pipelines.input_sanitizer import InputSanitizer
    if not dlp_client or not text:
        return InputSanitizer.scan_for_pii(text) if text else text
        
    try:
        from config import GCP_PROJECT_ID
        parent = f"projects/{GCP_PROJECT_ID}/locations/global"
        
        item = {"value": text}
        inspect_config = {
            "info_types": [
                {"name": "EMAIL_ADDRESS"},
                {"name": "PHONE_NUMBER"},
            ]
        }
        deidentify_config = {
            "info_type_transformations": {
                "transformations": [
                    {
                        "primitive_transformation": {
                            "replace_with_info_type_config": {}
                        }
                    }
                ]
            }
        }
        
        response = dlp_client.deidentify_content(
            request={
                "parent": parent,
                "deidentify_config": deidentify_config,
                "inspect_config": inspect_config,
                "item": item,
            }
        )
        return response.item.value
    except Exception as e:
        print(f"DLP redaction failed: {e}")
        return InputSanitizer.scan_for_pii(text)


def log_pipeline_event(user_id: str, pipeline_name: str, message: str, status: str = "info"):
    """
    Log a pipeline execution event.
    These appear in the dashboard's "Pipeline Execution Log" panel.
    """
    message = redact_pii(message)
    get_user_ref(user_id).collection("pipeline_logs").add({
        "pipeline": pipeline_name,
        "message": message,
        "status": status,  # "info", "success", "error"
        "timestamp": datetime.now(timezone.utc),
    })


def get_recent_pipeline_logs(user_id: str, limit: int = 100) -> list[dict]:
    """Get the most recent pipeline log entries."""
    docs = (
        get_user_ref(user_id)
        .collection("pipeline_logs")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


def save_agent_trace(user_id: str, pipeline_name: str, trace_data: list):
    """
    Save pipeline logs for debugging.

    This persists the chain of thoughts and results
    so we can review the reasoning process.

    Args:
        user_id: The user's unique identifier
        pipeline_name: Which pipeline generated this trace
        trace_data: List of trace events (thoughts, tool_calls, results, errors)
    """
    try:
        # Redact the entire trace stringified to catch PII in tool arguments or thoughts
        trace_str = json.dumps(trace_data)
        redacted_str = redact_pii(trace_str)
        trace_data = json.loads(redacted_str)
    except Exception as e:
        print(f"Failed to redact trace data: {e}")
        
    trace_doc = {
        "pipeline": pipeline_name,
        "trace": trace_data,
        "step_count": len(trace_data),
        "created_at": datetime.now(timezone.utc),
    }
    get_user_ref(user_id).collection("agent_traces").add(trace_doc)


# ══════════════════════════════════════════════
# User Profile
# ══════════════════════════════════════════════

def save_user_profile(user_id: str, profile_data: dict):
    """Save or update the user's hair profile."""
    profile_data["updated_at"] = datetime.now(timezone.utc)
    get_user_ref(user_id).collection("profile").document("hair").set(
        profile_data, merge=True  # merge=True means update fields, don't overwrite
    )


def get_user_profile(user_id: str) -> dict | None:
    """Get the user's hair profile."""
    doc = get_user_ref(user_id).collection("profile").document("hair").get()
    return doc.to_dict() if doc.exists else None


def get_user_location(user_id: str) -> dict:
    """Get the user's location (lat/lon/city/timezone). Falls back to defaults."""
    from config import DEFAULT_LAT, DEFAULT_LON, DEFAULT_CITY
    user_doc = db.collection("users").document(user_id).get()
    if user_doc.exists:
        data = user_doc.to_dict()
        location = data.get("location", {})
        if location.get("latitude") and location.get("longitude"):
            # Ensure timezone has a fallback
            location.setdefault("timezone", "UTC")
            return location
    return {"latitude": DEFAULT_LAT, "longitude": DEFAULT_LON, "city": DEFAULT_CITY, "timezone": "UTC"}


def get_user_email(user_id: str) -> str:
    """Get the user's email."""
    doc = db.collection("users").document(user_id).get()
    if doc.exists:
        return doc.to_dict().get("email", f"{user_id}@curlchemist.app")
    return f"{user_id}@curlchemist.app"


def get_recent_alerts(user_id: str, limit: int = 10) -> list[dict]:
    """Get the user's recent shopping alerts."""
    docs = (
        get_user_ref(user_id)
        .collection("alerts")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


def get_recent_calendar_events(user_id: str, limit: int = 10) -> list[dict]:
    """Get the user's scheduled calendar events."""
    docs = (
        get_user_ref(user_id)
        .collection("calendar_events")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

# ══════════════════════════════════════════════
# GCS to Gemini Part Helper
# ══════════════════════════════════════════════
def get_part_from_gcs_uri(uri: str, mime_type: str = "image/jpeg"):
    """
    Returns a types.Part for Gemini.
    If GEMINI_API_KEY is set (using AI Studio), downloads bytes directly.
    Otherwise uses Part.from_uri (Vertex AI native).
    """
    from config import GEMINI_API_KEY
    from google.genai import types
    if GEMINI_API_KEY:
        path = uri.replace(f"gs://{PHOTOS_BUCKET}/", "")
        blob = bucket.blob(path)
        return types.Part.from_bytes(data=blob.download_as_bytes(), mime_type=mime_type)
    return types.Part.from_uri(file_uri=uri, mime_type=mime_type)