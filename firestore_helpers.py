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


def create_user(username: str, hair_profile: dict, location: dict, photo_url: str = None) -> dict:
    """
    Create a new user account.

    Args:
        username: unique username (used as document ID)
        hair_profile: dict with hair_type, porosity, protein_sensitivity, etc.
        location: dict with city, latitude, longitude
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

def save_conflict(user_id: str, conflict_data: dict) -> str:
    """Save a detected conflict."""
    conflict_data["detected_at"] = datetime.now(timezone.utc)
    conflict_data["resolved"] = False
    doc_ref = get_user_ref(user_id).collection("conflicts").document()
    doc_ref.set(conflict_data)
    return doc_ref.id


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

def log_pipeline_event(user_id: str, pipeline_name: str, message: str, status: str = "info"):
    """
    Log a pipeline execution event.
    These appear in the dashboard's "Pipeline Execution Log" panel.
    """
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
    """Get the user's location (lat/lon/city). Falls back to defaults."""
    from config import DEFAULT_LAT, DEFAULT_LON, DEFAULT_CITY
    user_doc = db.collection("users").document(user_id).get()
    if user_doc.exists:
        data = user_doc.to_dict()
        location = data.get("location", {})
        if location.get("latitude") and location.get("longitude"):
            return location
    return {"latitude": DEFAULT_LAT, "longitude": DEFAULT_LON, "city": DEFAULT_CITY}