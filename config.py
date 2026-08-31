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

IS_DEV = os.getenv("IS_DEV", "false").lower() == "true"

# ── Google Cloud ──
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "curl-chemist")
# Aligning default with your local .env
GCP_REGION = os.getenv("GCP_REGION", "europe-west2")

# ── Gemini ──
# IMPORTANT: Verify this model ID in Vertex AI Model Garden before coding.
# Go to: https://console.cloud.google.com/vertex-ai/model-garden
# Search for "Gemini" and find the exact model ID string.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-2-9b-it")
GEMMA_REGION = os.getenv("GEMMA_REGION", GCP_REGION)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", None)

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
# Open-Meteo is free, no API key needed.
# Location coordinates are now stored per-user in their profile.
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"

# ── Default location (fallback if user hasn't set location) ──
DEFAULT_LAT = 30.0444
DEFAULT_LON = 31.2357
DEFAULT_CITY = "Cairo"