from google.cloud import firestore
from datetime import datetime, timezone
from config import DEMO_USER_ID

# Initialize the Firestore client once, reuse everywhere
db = firestore.Client()


def get_user_ref():
    """Get a reference to the current user's document."""
    return db.collection("users").document(DEMO_USER_ID)


# ── Products ──

def save_product(product_data: dict) -> str:
    """
    Save a scanned product to the user's shelf.
    Returns the auto-generated document ID.
    """
    product_data["scanned_at"] = datetime.now(timezone.utc)
    doc_ref = get_user_ref().collection("products").document()
    doc_ref.set(product_data)
    return doc_ref.id


def get_all_products() -> list[dict]:
    """Get all products on the user's shelf."""
    docs = get_user_ref().collection("products").stream()
    products = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        products.append(data)
    return products


def delete_product(product_id: str):
    """
    Delete a product from the user's shelf.
    Also clears any conflicts that involved this product.
    """
    get_user_ref().collection("products").document(product_id).delete()
    clear_conflicts_for_product(product_id)


def clear_conflicts_for_product(product_id: str):
    """Remove all conflicts that involve a specific product."""
    conflicts_ref = get_user_ref().collection("conflicts")

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


def clear_all_conflicts():
    """Clear all conflicts. Used before a full shelf re-analysis."""
    docs = get_user_ref().collection("conflicts").stream()
    for doc in docs:
        doc.reference.delete()


# ── Routines ──

def save_routine(date_str: str, routine_data: dict):
    """
    Save a generated routine for a specific date.
    Uses the date as the document ID → idempotent.
    (If the pipeline runs twice for the same date, it overwrites, not duplicates.)
    """
    routine_data["generated_at"] = datetime.now(timezone.utc)
    routine_data["generated_by"] = "nightly_pipeline"
    get_user_ref().collection("routines").document(date_str).set(routine_data)


def get_routine(date_str: str) -> dict | None:
    """Get the routine for a specific date."""
    doc = get_user_ref().collection("routines").document(date_str).get()
    return doc.to_dict() if doc.exists else None


def get_latest_routine() -> dict | None:
    """Get the most recently generated routine."""
    docs = (
        get_user_ref()
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

def save_conflict(conflict_data: dict) -> str:
    """Save a detected conflict."""
    conflict_data["detected_at"] = datetime.now(timezone.utc)
    conflict_data["resolved"] = False
    doc_ref = get_user_ref().collection("conflicts").document()
    doc_ref.set(conflict_data)
    return doc_ref.id


def get_active_conflicts() -> list[dict]:
    """Get all unresolved conflicts."""
    docs = (
        get_user_ref()
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


# ── Wash History ──

def save_wash_entry(entry_data: dict) -> str:
    """Save a wash day entry with photo analysis."""
    entry_data["created_at"] = datetime.now(timezone.utc)
    doc_ref = get_user_ref().collection("wash_history").document()
    doc_ref.set(entry_data)
    return doc_ref.id


def get_recent_wash_history(days: int = 7) -> list[dict]:
    """Get wash history entries from the last N days."""
    cutoff = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0
    )
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)

    docs = (
        get_user_ref()
        .collection("wash_history")
        .where("created_at", ">=", cutoff)
        .order_by("created_at")
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


# ── Reports ──

def save_weekly_report(week_str: str, report_data: dict):
    """Save a weekly health report. Idempotent by week string."""
    report_data["generated_at"] = datetime.now(timezone.utc)
    report_data["generated_by"] = "weekly_pipeline"
    get_user_ref().collection("reports").document(f"weekly_{week_str}").set(
        report_data
    )


def get_latest_report() -> dict | None:
    """Get the most recent weekly report."""
    docs = (
        get_user_ref()
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


# ── Pipeline Logs ──

def log_pipeline_event(pipeline_name: str, message: str, status: str = "info"):
    """
    Log a pipeline execution event.
    These appear in the dashboard's "Pipeline Execution Log" panel.
    """
    get_user_ref().collection("pipeline_logs").add({
        "pipeline": pipeline_name,
        "message": message,
        "status": status,  # "info", "success", "error"
        "timestamp": datetime.now(timezone.utc),
    })


def get_recent_pipeline_logs(limit: int = 20) -> list[dict]:
    """Get the most recent pipeline log entries."""
    docs = (
        get_user_ref()
        .collection("pipeline_logs")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


# ── User Profile ──

def save_user_profile(profile_data: dict):
    """Save or update the user's hair profile."""
    profile_data["updated_at"] = datetime.now(timezone.utc)
    get_user_ref().collection("profile").document("hair").set(
        profile_data, merge=True  # merge=True means update fields, don't overwrite
    )


def get_user_profile() -> dict | None:
    """Get the user's hair profile."""
    doc = get_user_ref().collection("profile").document("hair").get()
    return doc.to_dict() if doc.exists else None