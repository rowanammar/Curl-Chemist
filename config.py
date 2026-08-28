"""
Central configuration for Curl Chemist.

WHY THIS FILE EXISTS:
Instead of scattering environment variables across 10 files,
we read them all in ONE place. Every other file imports from here.
If something changes (like the Gemini model ID), you change it in one spot.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Reads .env file during local development

# ── Google Cloud ──
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "curl-chemist")
GCP_REGION = os.getenv("GCP_REGION", "europe-west1")

# ── Gemini ──
# IMPORTANT: Verify this model ID in Vertex AI Model Garden before coding.
# Go to: https://console.cloud.google.com/vertex-ai/model-garden
# Search for "Gemini" and find the exact model ID string.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")

# ── Firestore ──
# No special config needed — the client auto-detects project ID
# when running on Cloud Run. Locally, it uses your gcloud auth.

# ── Cloud Storage ──
PHOTOS_BUCKET = os.getenv("PHOTOS_BUCKET", "curl-chemist-photos")

# ── Pub/Sub Topics ──
TOPIC_NIGHTLY = "nightly-routine-trigger"
TOPIC_SHELF_UPDATED = "shelf-updated"
TOPIC_WEEKLY_HEALTH = "weekly-health-trigger"
TOPIC_USER_ALERTS = "user-alerts"

# ── Weather ──
# Open-Meteo is free, no API key needed, and has Cairo data.
# We use Cairo's coordinates.
CAIRO_LAT = 30.0444
CAIRO_LON = 31.2357
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# ── Demo User ──
# For the hackathon, we use a single hardcoded user ID.
# In production, this would come from authentication.
DEMO_USER_ID = "rawan"