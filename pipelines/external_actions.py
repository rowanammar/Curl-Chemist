"""
External Actions — Real-world tools the agent can trigger autonomously.

WHY THIS FILE EXISTS:
The Taskmaster rubric demands the agent "takes action" and "sends info
to the right places." These tools generate external artifacts:
1. .ics calendar events for wash day scheduling
2. Mock email/SMS shopping alerts for missing necessities

The agent decides WHEN to call these based on its analysis —
e.g., if tomorrow's routine requires deep conditioning, it blocks
45 minutes on the calendar. If the shelf has heavy silicones but
no clarifying shampoo, it proactively alerts the user to buy one.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from firestore_helpers import log_pipeline_event, get_user_ref, get_user_email
from google_api_service import send_gmail, create_calendar_event


def schedule_calendar_event(
    user_id: str,
    event_title: str,
    event_description: str,
    duration_minutes: int = 45,
    date_str: str = "",
) -> dict:
    """Schedule a calendar event for the user's hair care routine.

    Use this tool when the generated routine includes a time-intensive
    step like a deep conditioning treatment, wash day, or protein
    treatment. Creates an .ics calendar file the user can import.

    Args:
        user_id: The user's unique identifier
        event_title: Title of the event (e.g., "Wash Day Routine — Deep Conditioning")
        event_description: Detailed description with routine steps
        duration_minutes: How long to block (default: 45 minutes)
        date_str: Date in YYYY-MM-DD format (defaults to tomorrow)

    Returns:
        dict with ics_content, event_id, and confirmation message.
    """
    # Default to tomorrow if no date provided
    if not date_str:
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        date_str = tomorrow.strftime("%Y-%m-%d")

    # Parse the date and set a reasonable start time (8:00 AM)
    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=8, minute=0, second=0, tzinfo=timezone.utc
        )
    except ValueError:
        event_date = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
            hour=8, minute=0, second=0
        )

    event_end = event_date + timedelta(minutes=duration_minutes)
    event_uid = str(uuid4())

    # Generate standard iCalendar (.ics) content
    sanitized_desc = event_description.replace(chr(10), '\\n')
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Curl Chemist//Taskmaster Agent//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{event_uid}
DTSTART:{event_date.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{event_end.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:{event_title}
DESCRIPTION:{sanitized_desc}
STATUS:CONFIRMED
ORGANIZER:CN=Curl Chemist Agent
BEGIN:VALARM
TRIGGER:-PT15M
ACTION:DISPLAY
DESCRIPTION:Reminder: {event_title}
END:VALARM
END:VEVENT
END:VCALENDAR"""

    # Persist to Firestore
    event_data = {
        "event_id": event_uid,
        "title": event_title,
        "description": event_description,
        "date": date_str,
        "start_time": event_date.isoformat(),
        "end_time": event_end.isoformat(),
        "duration_minutes": duration_minutes,
        "ics_content": ics_content,
        "created_at": datetime.now(timezone.utc),
        "created_by": "taskmaster_agent",
        "status": "scheduled",
    }

    get_user_ref(user_id).collection("calendar_events").document(event_uid).set(event_data)

    # Call real Google Calendar API
    user_email = get_user_email(user_id)
    try:
        api_res = create_calendar_event(
            attendee_email=user_email,
            title=event_title,
            description=event_description,
            start_time=event_date.isoformat(),
            end_time=event_end.isoformat(),
        )
    except Exception as e:
        log_pipeline_event(
            user_id, "external_action",
            f"[CALENDAR] Failed to schedule '{event_title}' via Google API: {e}",
            status="error",
        )
        return {
            "status": "failed",
            "event_id": event_uid,
            "message": f"Failed to schedule calendar event: {e}"
        }

    # Log as pipeline event for observability
    log_pipeline_event(
        user_id, "external_action",
        f"[CALENDAR] Scheduled '{event_title}' on {date_str} for {duration_minutes}min via Google API",
        status="success",
    )

    return {
        "status": "scheduled",
        "event_id": event_uid,
        "message": f"Calendar event '{event_title}' scheduled. Google API Link: {api_res.get('link', 'Check Email')}",
    }


def dispatch_shopping_alert(
    user_id: str,
    alert_title: str,
    alert_body: str,
    recommended_product_type: str,
    low_cost_option: str = "",
    premium_option: str = "",
    local_option: str = "",
    urgency: str = "high",
    trigger_reason: str = "",
) -> dict:
    """Send a proactive shopping alert when a critical product is missing.

    Use this tool when conflict analysis reveals the user is missing a
    necessity. This generates a REAL email notification using the Gmail API
    advising the user what to buy, including specific recommendations.

    Args:
        user_id: The user's unique identifier
        alert_title: Alert headline (e.g., "Missing: Clarifying Shampoo")
        alert_body: Detailed explanation of why the product is needed
        recommended_product_type: Type of product to buy (e.g., "clarifying_shampoo")
        low_cost_option: Name of a budget-friendly option
        premium_option: Name of a high-end option
        local_option: Name of an Egyptian/local option
        urgency: Alert urgency level — "high", "medium", or "low"
        trigger_reason: What conflict triggered this alert

    Returns:
        dict with alert_id and confirmation.
    """
    alert_id = str(uuid4())
    user_email = get_user_email(user_id)

    # Prevent spam: if an unacknowledged alert for this product type already exists, skip.
    existing_alerts = get_user_ref(user_id).collection("alerts").where("acknowledged", "==", False).where("recommended_product_type", "==", recommended_product_type).limit(1).stream()
    for doc in existing_alerts:
        return {
            "status": "skipped",
            "message": f"Active alert for {recommended_product_type} already exists. Skipped duplicate."
        }

    email_html = (
        f"<h2>⚠️ {alert_title}</h2>"
        f"<p>{alert_body}</p>"
        f"<p><strong>Recommended Product Type:</strong> {recommended_product_type}</p>"
        f"<h3>Top Recommendations:</h3>"
        f"<ul>"
        f"<li><strong>Local Egyptian Choice:</strong> {local_option or 'N/A'}</li>"
        f"<li><strong>Budget Choice:</strong> {low_cost_option or 'N/A'}</li>"
        f"<li><strong>Premium Choice:</strong> {premium_option or 'N/A'}</li>"
        f"</ul>"
        f"<p><em>Trigger: {trigger_reason}</em></p>"
    )

    # Persist to Firestore
    alert_data = {
        "alert_id": alert_id,
        "title": alert_title,
        "body": alert_body,
        "recommended_product_type": recommended_product_type,
        "urgency": urgency,
        "trigger_reason": trigger_reason,
        "created_at": datetime.now(timezone.utc),
        "created_by": "taskmaster_agent",
        "status": "dispatched",
        "acknowledged": False,
    }

    get_user_ref(user_id).collection("alerts").document(alert_id).set(alert_data)

    # Call real Gmail API
    subject = f"🚨 Curl Chemist Alert: {alert_title}"
    try:
        api_res = send_gmail(user_email, subject, email_html)
    except Exception as e:
        log_pipeline_event(
            user_id, "external_action",
            f"[SHOPPING ALERT] Failed to dispatch email to {user_email}: {e}",
            status="error",
        )
        return {
            "status": "failed",
            "alert_id": alert_id,
            "message": f"Failed to send email alert: {e}",
        }

    # Log as pipeline event for observability
    log_pipeline_event(
        user_id, "external_action",
        f"[SHOPPING ALERT] Dispatched real email to {user_email}: {alert_title}",
        status="warning" if urgency == "high" else "info",
    )

    return {
        "status": "dispatched",
        "alert_id": alert_id,
        "message": f"Shopping alert real email dispatched to {user_email}. Gmail API ID: {api_res.get('message_id', 'unknown')}",
    }
