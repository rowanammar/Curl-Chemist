# ⚗️ CURL CHEMIST — Complete Build Guide

> **Who this is for:** You know programming. You know what cloud is conceptually. You may NOT have wired all these specific Google services together before. This guide explains every piece, why it exists, and how to build it — step by step.

---

## Table of Contents

1. [What Are We Actually Building?](#1-what-are-we-actually-building)
2. [The Tech Stack — What Each Piece Does and Why](#2-the-tech-stack)
3. [Prerequisites — What You Need Before Writing Code](#3-prerequisites)
4. [GCP Project Setup](#4-gcp-project-setup)
5. [Project Structure](#5-project-structure)
6. [Phase 1: The Foundation](#6-phase-1-the-foundation)
7. [Phase 2: The Agents](#7-phase-2-the-agents)
8. [Phase 3: The Pipelines](#8-phase-3-the-pipelines)
9. [Phase 4: The Dashboard](#9-phase-4-the-dashboard)
10. [Phase 5: Deployment](#10-phase-5-deployment)
11. [Phase 6: Cloud Scheduler + Pub/Sub Wiring](#11-phase-6-cloud-scheduler--pubsub-wiring)
12. [Phase 7: Testing Everything](#12-phase-7-testing-everything)
13. [Phase 8: Demo, Docs, Ship](#13-phase-8-demo-docs-ship)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. What Are We Actually Building?

Forget the fancy names for a second. Here's what the system does in plain English:

1. **You take a photo of a hair product.** The system reads the ingredient list from the photo, figures out what each ingredient does, and saves it.
2. **The system checks if your products fight each other.** Some ingredients cancel each other out or cause damage when combined. The system checks ALL your products against each other automatically.
3. **Every night, the system checks tomorrow's weather** and generates a personalized hair routine for you. High humidity? Skip the glycerin. High UV? Add sun protection. You wake up and the routine is waiting.
4. **Every week, the system analyzes your hair progress photos** and figures out what's working and what isn't. It adjusts your future routines based on real results.

**You interact with it for 5 minutes (onboarding + scanning products). Everything else runs by itself, 24/7, while you sleep.**

That's it. That's the whole system. Everything below is HOW to build it.

---

## 2. The Tech Stack

Here's every technology we're using, what it does, and WHY we chose it specifically.

### The AI Layer

| Technology | What it is | What it does in our system |
|---|---|---|
| **Gemini 3.5 Flash** (via Vertex AI) | Google's latest multimodal AI model. "Multimodal" means it understands both text AND images. | Reads ingredient lists from product photos (vision). Generates personalized routines (text). Analyzes hair selfies for health scoring (vision). Powers the collaborative hair profile interview (text). |
| **Google ADK** (Agent Development Kit) | A Python framework for building AI agents. An "agent" is an AI that can use tools and take actions, not just chat. | Defines our 4 specialized agents (Scanner, Chemist, Climate, Profiler). Each agent has specific tools it's allowed to use. ADK handles routing between agents. |
| **Gemma** (optional bonus) | A smaller, lighter Google AI model. | Pre-classifies ingredients before sending to Gemini. Earns +0.2 bonus points. |

### The Cloud Infrastructure Layer

| Technology | What it is | What it does in our system | Why not something else? |
|---|---|---|---|
| **Cloud Run** | A service that runs your code in a container on Google's servers. You don't manage any servers. It auto-scales (even to zero when idle = cheap). | Hosts our entire backend: the API, the agents, and the pipeline jobs. | It's the simplest way to deploy. No server management. Pay only when running. |
| **Firestore** | A NoSQL document database. Think of it as a giant JSON file that's fast, scalable, and lives in the cloud. | Stores EVERYTHING: products, user profiles, routines, conflicts, health reports, pipeline logs. | It's schemaless (flexible), real-time (dashboard updates instantly), and has a generous free tier. |
| **Pub/Sub** | A messaging service. One part of your system "publishes" a message, another part "subscribes" and reacts to it. | Connects the pipelines: "new product uploaded" → triggers reanalysis. "routine generated" → triggers notification. Decouples the system so parts can fail independently. | It's how you make things event-driven instead of request-response. Critical for the "autonomous" story. |
| **Cloud Scheduler** | A managed cron job service. It fires at times you specify. | Triggers Pipeline 1 at 9 PM daily. Triggers Pipeline 3 every Sunday at 8 PM. | You need SOMETHING to wake up your pipelines on a schedule. This is Google's built-in answer. |
| **Cloud Storage** | A file/object storage service (like a cloud hard drive). | Stores uploaded product photos and hair selfies. When a file is uploaded, it can trigger events (this is how Pipeline 2 starts). | It integrates with Pub/Sub natively — upload a file, get an automatic event. |

### How They Connect (the data flow)

```
User snaps photo
    → Photo lands in Cloud Storage
    → Cloud Storage sends event to Pub/Sub ("new file uploaded")
    → Pub/Sub triggers Cloud Run endpoint
    → Cloud Run calls Scanner Agent (Gemini Vision reads the label)
    → Cloud Run calls Chemist Agent (checks conflicts against shelf)
    → Results written to Firestore
    → If critical conflict found → Pub/Sub sends alert notification
    → Dashboard reads from Firestore and shows updated data

Meanwhile, on a schedule:
    Cloud Scheduler fires at 9 PM
    → Sends message to Pub/Sub ("time for nightly routine")
    → Pub/Sub triggers Cloud Run endpoint
    → Cloud Run calls Climate Agent (fetches weather, generates routine)
    → Routine written to Firestore
    → Dashboard shows tomorrow's routine when user opens it
```

---

## 3. Prerequisites

### Software you need installed

```powershell
# 1. Python 3.11+ (check with:)
python --version

# 2. Google Cloud CLI (gcloud)
# Download from: https://cloud.google.com/sdk/docs/install
# After installing, verify:
gcloud --version

# 3. Docker Desktop (for containerizing your app)
# Download from: https://www.docker.com/products/docker-desktop/
# After installing, verify:
docker --version

# 4. Git
git --version
```

### Accounts you need

- **Google Cloud account** with billing enabled (you need a credit card, but you'll set a budget alert so you don't get surprised)
- **GitHub account** for the code repository
- **Devpost account** for the submission
- **dev.to account** for the blog post (bonus +0.2)

---

## 4. GCP Project Setup

This creates all the Google Cloud resources your app needs. Run these in PowerShell.

### Step 1: Create the project and set it as active

```powershell
# Pick a unique project ID (must be globally unique across all of Google Cloud)
# Replace "curl-chemist-rawan" with something unique to you
gcloud projects create curl-chemist-rawan --name="Curl Chemist"

# Set it as your active project (so all future commands target it)
gcloud config set project curl-chemist-rawan
```

### Step 2: Link billing

```powershell
# List your billing accounts to find the ID
gcloud billing accounts list

# Link it (replace BILLING_ACCOUNT_ID with the actual ID from above)
gcloud billing projects link curl-chemist-rawan --billing-account=BILLING_ACCOUNT_ID
```

### Step 3: Enable all the APIs we need

Each Google Cloud service has an API that must be explicitly turned on. Think of it like flipping switches.

```powershell
gcloud services enable `
  run.googleapis.com `
  firestore.googleapis.com `
  pubsub.googleapis.com `
  cloudscheduler.googleapis.com `
  storage.googleapis.com `
  aiplatform.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com
```

**What each API does:**
- `run.googleapis.com` — Cloud Run (hosts your code)
- `firestore.googleapis.com` — Firestore (your database)
- `pubsub.googleapis.com` — Pub/Sub (event messaging)
- `cloudscheduler.googleapis.com` — Cloud Scheduler (cron jobs)
- `storage.googleapis.com` — Cloud Storage (file storage)
- `aiplatform.googleapis.com` — Vertex AI (Gemini access)
- `cloudbuild.googleapis.com` — Cloud Build (builds your Docker container)
- `artifactregistry.googleapis.com` — Artifact Registry (stores your Docker image)

### Step 4: Create Firestore database

```powershell
# Create a Firestore database in Native mode (not Datastore mode!)
# "Native mode" gives you real-time listeners, which the dashboard uses
gcloud firestore databases create --location=europe-west1
```

> [!TIP]
> **Why `europe-west1`?** It's the closest region to Cairo. Lower latency = faster responses. You can also use `me-central1` (Doha) if available, or `europe-west4` (Netherlands).

### Step 5: Create Cloud Storage bucket

```powershell
# Create a bucket for product photos and hair selfies
# Bucket name must be globally unique — use your project ID
gcloud storage buckets create gs://curl-chemist-rawan-photos --location=europe-west1
```

### Step 6: Create Pub/Sub topics and subscriptions

```powershell
# Topic 1: Triggers nightly routine generation
gcloud pubsub topics create nightly-routine-trigger

# Topic 2: Triggers shelf reanalysis when a new product is scanned
gcloud pubsub topics create shelf-updated

# Topic 3: Triggers weekly health analysis
gcloud pubsub topics create weekly-health-trigger

# Topic 4: Sends alerts to the user (conflicts, low stock, etc.)
gcloud pubsub topics create user-alerts
```

### Step 7: Set up Cloud Storage notification

This makes Cloud Storage automatically send a Pub/Sub message whenever a file is uploaded to your bucket.

```powershell
# When any file is uploaded to the photos bucket, notify the shelf-updated topic
gcloud storage buckets notifications create gs://curl-chemist-rawan-photos `
  --topic=shelf-updated `
  --event-types=OBJECT_FINALIZE
```

### Step 8: Set a billing budget alert

```powershell
# Do this in the console (easier with UI):
# 1. Go to https://console.cloud.google.com/billing
# 2. Click your billing account → Budgets & alerts
# 3. Create budget: $25 threshold, email alerts at 50%, 80%, 100%
```

### Step 9: Create a service account

The service account is the "identity" your Cloud Run service uses to access other Google services. Think of it as a robot employee with specific permissions.

```powershell
# Create the service account
gcloud iam service-accounts create curl-chemist-sa `
  --display-name="Curl Chemist Service Account"

# Give it the permissions it needs:
# Firestore read/write
gcloud projects add-iam-policy-binding curl-chemist-rawan `
  --member="serviceAccount:curl-chemist-sa@curl-chemist-rawan.iam.gserviceaccount.com" `
  --role="roles/datastore.user"

# Cloud Storage read/write
gcloud projects add-iam-policy-binding curl-chemist-rawan `
  --member="serviceAccount:curl-chemist-sa@curl-chemist-rawan.iam.gserviceaccount.com" `
  --role="roles/storage.objectUser"

# Pub/Sub publish
gcloud projects add-iam-policy-binding curl-chemist-rawan `
  --member="serviceAccount:curl-chemist-sa@curl-chemist-rawan.iam.gserviceaccount.com" `
  --role="roles/pubsub.publisher"

# Vertex AI user (to call Gemini)
gcloud projects add-iam-policy-binding curl-chemist-rawan `
  --member="serviceAccount:curl-chemist-sa@curl-chemist-rawan.iam.gserviceaccount.com" `
  --role="roles/aiplatform.user"
```

---

## 5. Project Structure

Create this folder structure. Every file is explained below.

```
curl-chemist/
│
├── agents/                     # The 4 AI agents
│   ├── __init__.py
│   ├── scanner_agent.py        # Reads product labels via Gemini Vision
│   ├── chemist_agent.py        # Detects ingredient conflicts
│   ├── climate_agent.py        # Fetches weather, generates routines
│   └── profiler_agent.py       # Analyzes hair health trends
│
├── pipelines/                  # The 3 autonomous background pipelines
│   ├── __init__.py
│   ├── nightly_routine.py      # Pipeline 1: runs at 9 PM
│   ├── shelf_reanalysis.py     # Pipeline 2: runs on product upload
│   └── weekly_health.py        # Pipeline 3: runs every Sunday
│
├── data/
│   └── conflict_rules.json     # 15+ ingredient conflict rules
│
├── dashboard/
│   ├── static/
│   │   ├── style.css
│   │   └── app.js
│   └── templates/
│       └── index.html
│
├── main.py                     # FastAPI app — the single entry point
├── config.py                   # All configuration / env vars
├── firestore_helpers.py        # Reusable Firestore read/write functions
├── Dockerfile                  # Container definition for Cloud Run
├── requirements.txt            # Python dependencies
├── .env.example                # Template for environment variables
└── README.md                   # Setup instructions + architecture diagram
```

---

## 6. Phase 1: The Foundation

These are the files that everything else depends on. Build these first.

### 6.1 `requirements.txt`

```txt
# Web framework — handles HTTP requests, serves the dashboard
fastapi==0.115.0
uvicorn[standard]==0.30.0

# Google Cloud libraries
google-cloud-firestore==2.19.0
google-cloud-storage==2.18.0
google-cloud-pubsub==2.23.0

# Google AI
google-genai==1.14.0
google-adk==1.3.0

# HTTP requests (for weather API)
httpx==0.28.0

# Templating (for the dashboard HTML)
jinja2==3.1.4

# Environment variable management
python-dotenv==1.0.1
```

> [!NOTE]
> **Pin your versions.** If you just write `fastapi` without a version, pip might install a newer version that breaks something. The versions above are known-good as of mid-2026 — adjust if needed.

### 6.2 `config.py`

This file centralizes ALL configuration. Nothing is hardcoded anywhere else.

```python
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
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "curl-chemist-rawan")
GCP_REGION = os.getenv("GCP_REGION", "europe-west1")

# ── Gemini ──
# IMPORTANT: Verify this model ID in Vertex AI Model Garden before coding.
# Go to: https://console.cloud.google.com/vertex-ai/model-garden
# Search for "Gemini" and find the exact model ID string.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ── Firestore ──
# No special config needed — the client auto-detects project ID
# when running on Cloud Run. Locally, it uses your gcloud auth.

# ── Cloud Storage ──
PHOTOS_BUCKET = os.getenv("PHOTOS_BUCKET", "curl-chemist-rawan-photos")

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
```

### 6.3 `.env.example`

```env
GCP_PROJECT_ID=curl-chemist-rawan
GCP_REGION=europe-west1
GEMINI_MODEL=gemini-2.5-flash
PHOTOS_BUCKET=curl-chemist-rawan-photos
```

Copy this to `.env` and fill in your actual values:
```powershell
copy .env.example .env
```

### 6.4 `firestore_helpers.py`

Reusable functions for reading and writing to Firestore. Every pipeline and agent uses these.

```python
"""
Firestore helper functions.

WHY THIS FILE EXISTS:
Every pipeline and agent needs to read/write Firestore.
Instead of duplicating Firestore code everywhere, we centralize it here.
This also means if Firestore's API changes, we fix it in one place.

HOW FIRESTORE WORKS (quick primer):
- Firestore stores data as "documents" inside "collections"
- A document is like a JSON object (key-value pairs)
- A collection is like a folder of documents
- Path example: users/rawan/products/product123
  → collection "users" → document "rawan" → sub-collection "products" → document "product123"
"""

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


# ── Conflicts ──

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
```

### 6.5 `data/conflict_rules.json`

This is the ingredient conflict knowledge base. The Chemist Agent uses these rules instead of hallucinating conflicts.

```json
[
  {
    "id": "silicone_sulfate_free",
    "type": "silicone_buildup",
    "trigger_a": {"category": "non_water_soluble_silicone", "examples": ["dimethicone", "cyclomethicone", "amodimethicone", "trimethylsilylamodimethicone"]},
    "trigger_b": {"category": "sulfate_free_cleanser", "examples": ["cocamidopropyl betaine", "decyl glucoside", "sodium cocoyl isethionate"]},
    "severity": "critical",
    "explanation": "Non-water-soluble silicones like {a} create a coating that sulfate-free shampoos cannot remove. This causes progressive buildup, making hair limp, greasy, and unable to absorb moisture.",
    "fix": "Either switch to a water-soluble silicone (like dimethicone copolyol or PEG-modified silicones) or use a clarifying shampoo with sulfates once every 2 weeks to remove buildup."
  },
  {
    "id": "protein_overload",
    "type": "protein_excess",
    "trigger_a": {"category": "protein", "examples": ["hydrolyzed keratin", "hydrolyzed wheat protein", "hydrolyzed silk", "amino acids", "collagen"]},
    "trigger_b": {"category": "protein", "examples": ["hydrolyzed keratin", "hydrolyzed wheat protein", "hydrolyzed silk", "amino acids", "collagen"]},
    "severity": "warning",
    "explanation": "Both products contain proteins ({a} and {b}). Using multiple protein-heavy products in the same routine can cause protein overload — hair becomes stiff, brittle, and snaps easily. This is especially risky for low-porosity hair.",
    "fix": "Use only ONE protein-containing product per wash day. Alternate with a protein-free moisturizing product."
  },
  {
    "id": "humectant_high_humidity",
    "type": "climate_interaction",
    "trigger_a": {"category": "humectant", "examples": ["glycerin", "propylene glycol", "honey", "agave", "aloe vera", "sodium hyaluronate", "hyaluronic acid"]},
    "condition": "humidity_above_65",
    "severity": "warning",
    "explanation": "Humectants like {a} attract moisture from the environment. In high humidity (>65%), they pull excess water into the hair shaft, causing swelling and frizz. Cairo's summer humidity regularly exceeds 65%.",
    "fix": "On high-humidity days, skip humectant-heavy products and use anti-humectant sealants (like oils or heavy butters) instead."
  },
  {
    "id": "humectant_low_humidity",
    "type": "climate_interaction",
    "trigger_a": {"category": "humectant", "examples": ["glycerin", "propylene glycol", "honey", "agave", "sodium hyaluronate"]},
    "condition": "humidity_below_30",
    "severity": "warning",
    "explanation": "In low humidity (<30%), humectants like {a} can't find moisture in the air, so they pull it FROM your hair instead — causing dryness and brittleness.",
    "fix": "In dry conditions, layer humectants UNDER a sealing oil or butter to lock moisture in rather than letting it escape."
  },
  {
    "id": "ph_clash",
    "type": "chemical_interaction",
    "trigger_a": {"category": "acidic_treatment", "examples": ["glycolic acid", "lactic acid", "citric acid", "apple cider vinegar"]},
    "trigger_b": {"category": "alkaline_product", "examples": ["sodium hydroxide", "calcium hydroxide", "baking soda", "soap-based cleanser"]},
    "severity": "critical",
    "explanation": "Your {a} product is acidic and your {b} product is alkaline. Using them in sequence neutralizes the acid treatment (wasting it) and creates unpredictable pH levels that can damage the hair cuticle.",
    "fix": "Never use acidic and alkaline products back-to-back. Wait at least 24 hours between them, or eliminate the alkaline product."
  },
  {
    "id": "oil_before_water",
    "type": "layering_error",
    "trigger_a": {"category": "oil_or_butter", "examples": ["coconut oil", "argan oil", "shea butter", "castor oil", "jojoba oil"]},
    "trigger_b": {"category": "water_based_product", "examples": ["aloe vera gel", "flaxseed gel", "water-based leave-in"]},
    "severity": "warning",
    "explanation": "If you apply oil/butter ({a}) BEFORE a water-based product ({b}), the oil creates a barrier that prevents the water-based product from penetrating. Your {b} just sits on top doing nothing.",
    "fix": "Always apply water-based products FIRST, then seal with oils/butters. Thin to thick, water to oil."
  },
  {
    "id": "alcohol_drying",
    "type": "ingredient_concern",
    "trigger_a": {"category": "drying_alcohol", "examples": ["alcohol denat", "isopropyl alcohol", "sd alcohol", "ethanol"]},
    "condition": "damaged_or_dry_hair",
    "severity": "warning",
    "explanation": "Your product contains {a}, a short-chain (drying) alcohol. On damaged or dry hair, this strips remaining moisture and worsens breakage.",
    "fix": "Look for products with fatty alcohols instead (cetyl alcohol, cetearyl alcohol, stearyl alcohol) — these are actually moisturizing, not drying."
  },
  {
    "id": "sulfate_color_treated",
    "type": "ingredient_concern",
    "trigger_a": {"category": "sulfate", "examples": ["sodium lauryl sulfate", "sodium laureth sulfate", "ammonium lauryl sulfate"]},
    "condition": "color_treated_hair",
    "severity": "critical",
    "explanation": "Sulfates like {a} are aggressive cleansers that strip color-treated hair, causing rapid fading and dryness.",
    "fix": "Switch to a sulfate-free cleanser. Look for gentle surfactants like cocamidopropyl betaine or decyl glucoside."
  },
  {
    "id": "competing_hold_polymers",
    "type": "redundancy",
    "trigger_a": {"category": "hold_polymer", "examples": ["PVP", "VP/VA copolymer", "polyquaternium-11", "polyquaternium-4"]},
    "trigger_b": {"category": "hold_polymer", "examples": ["PVP", "VP/VA copolymer", "polyquaternium-11", "polyquaternium-4"]},
    "severity": "info",
    "explanation": "Both products contain hold polymers ({a} and {b}). Using both doesn't give you double hold — it often creates flaking and stiffness as the polymers compete.",
    "fix": "Pick ONE hold product per wash day. If one has stronger hold than the other, use the lighter one for refresh days."
  },
  {
    "id": "mineral_oil_buildup",
    "type": "buildup_risk",
    "trigger_a": {"category": "mineral_oil", "examples": ["mineral oil", "paraffinum liquidum", "petrolatum", "petroleum jelly"]},
    "trigger_b": {"category": "sulfate_free_cleanser", "examples": ["cocamidopropyl betaine", "decyl glucoside"]},
    "severity": "warning",
    "explanation": "Mineral oil ({a}) creates a heavy, non-breathable coating similar to silicones. Your sulfate-free cleanser ({b}) cannot remove it effectively, leading to buildup.",
    "fix": "Use a clarifying shampoo periodically, or replace the mineral oil product with a plant-based oil (coconut, argan, jojoba)."
  },
  {
    "id": "heat_protectant_missing",
    "type": "missing_protection",
    "trigger_a": {"category": "heat_styling_tool_user"},
    "condition": "no_heat_protectant_in_shelf",
    "severity": "critical",
    "explanation": "You use heat styling tools but don't have a heat protectant in your product shelf. Unprotected heat application above 150°C causes irreversible protein denaturation — your hair literally cooks.",
    "fix": "Add a heat protectant spray or serum to your routine. Apply before ANY heat tool use."
  },
  {
    "id": "uv_no_protection",
    "type": "climate_interaction",
    "trigger_a": {"category": "any_product"},
    "condition": "uv_index_above_7_and_no_uv_filter",
    "severity": "warning",
    "explanation": "Cairo's UV index frequently exceeds 8. Prolonged UV exposure degrades hair proteins, fades color, and dries out the cuticle. None of your current products contain UV filters.",
    "fix": "Add a leave-in with UV filters, or physically protect hair with a hat/scarf on high-UV days."
  },
  {
    "id": "wax_buildup",
    "type": "buildup_risk",
    "trigger_a": {"category": "wax", "examples": ["beeswax", "candelilla wax", "carnauba wax", "microcrystalline wax"]},
    "trigger_b": {"category": "sulfate_free_cleanser", "examples": ["cocamidopropyl betaine", "decyl glucoside"]},
    "severity": "warning",
    "explanation": "Waxes like {a} are extremely difficult to remove without sulfate-based cleansers. Your sulfate-free shampoo ({b}) will leave wax residue, causing progressive weight and dullness.",
    "fix": "Avoid wax-based products if you're sulfate-free, or do a monthly clarifying wash."
  },
  {
    "id": "polyquat_film",
    "type": "buildup_risk",
    "trigger_a": {"category": "conditioning_polymer", "examples": ["polyquaternium-7", "polyquaternium-10", "guar hydroxypropyltrimonium chloride"]},
    "trigger_b": {"category": "conditioning_polymer", "examples": ["polyquaternium-7", "polyquaternium-10", "guar hydroxypropyltrimonium chloride"]},
    "severity": "info",
    "explanation": "Multiple products with conditioning polymers ({a}, {b}) can create layered films on hair. Over time, this makes hair feel coated, heavy, and unresponsive to products.",
    "fix": "Limit conditioning polymer products to one per routine. Clarify monthly to remove film buildup."
  },
  {
    "id": "keratin_moisture_imbalance",
    "type": "balance_issue",
    "trigger_a": {"category": "protein", "examples": ["hydrolyzed keratin", "keratin amino acids"]},
    "condition": "no_deep_conditioner_in_shelf",
    "severity": "warning",
    "explanation": "You're using keratin/protein treatments ({a}) but don't have a deep moisturizing conditioner in your shelf. Protein without sufficient moisture leads to brittle, straw-like hair. The protein-moisture balance is critical.",
    "fix": "Add a protein-free deep conditioner (look for one with shea butter, oils, and NO protein in the first 5 ingredients). Alternate: protein wash → moisture wash."
  }
]
```

---

## 7. Phase 2: The Agents

Each agent is a specialist with specific tools. ADK manages them.

### 7.1 `agents/__init__.py`

```python
"""Curl Chemist Agent Definitions."""
```

### 7.2 `agents/scanner_agent.py`

The Scanner Agent reads product labels from photos using Gemini Vision.

```python
"""
Scanner Agent — Extracts ingredients from product label photos.

WHAT THIS AGENT DOES:
1. Receives a product photo (uploaded to Cloud Storage)
2. Sends it to Gemini Vision to read the ingredient list
3. Classifies each ingredient by category
4. Returns structured product data

WHY IT'S A SEPARATE AGENT:
Tool isolation. The Scanner can read images and write to products,
but it CANNOT write routines or conflicts. This is a judging criterion
("properly isolated and scoped for security").
"""

from google import genai
from google.adk import Agent
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION

# Initialize the Gemini client via Vertex AI
client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)

SCANNER_INSTRUCTION = """You are the Scanner Agent of Curl Chemist.

Your job: Extract and classify ingredients from hair/skincare product label photos.

When given a product photo:
1. Read the full ingredient list from the label (handle Arabic, English, or mixed text)
2. For each ingredient, provide:
   - name: the ingredient name as written on the label
   - inci: the INCI (International Nomenclature of Cosmetic Ingredients) standard name
   - category: one of [silicone, protein, humectant, oil, butter, sulfate, preservative,
     fragrance, emulsifier, thickener, hold_polymer, conditioning_polymer, drying_alcohol,
     fatty_alcohol, wax, mineral_oil, uv_filter, acidic_treatment, alkaline_product, other]

3. Also extract: product name, brand name, and product type (shampoo, conditioner,
   leave-in, gel, mask, serum, oil, cream, spray)

If the label is unclear or you're not confident about an ingredient (confidence < 0.7),
mark it as "needs_review": true.

Return valid JSON only. No extra text.
"""


async def scan_product_label(image_uri: str) -> dict:
    """
    Scan a product label photo and extract structured ingredient data.

    Args:
        image_uri: Google Cloud Storage URI (gs://bucket/path/to/photo.jpg)

    Returns:
        dict with product_name, brand, product_type, ingredients list
    """
    from google.genai import types

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_uri(file_uri=image_uri, mime_type="image/jpeg"),
            types.Part.from_text(
                "Extract all ingredients from this product label photo. "
                "Return a JSON object with keys: product_name, brand, product_type, "
                "and ingredients (array of {name, inci, category, needs_review}). "
                "Handle Arabic and English text. If uncertain about any ingredient, "
                "set needs_review to true."
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,  # Low temp = more deterministic/accurate
        ),
    )

    import json
    return json.loads(response.text)


# Define the ADK agent
scanner_agent = Agent(
    name="scanner",
    model=GEMINI_MODEL,
    instruction=SCANNER_INSTRUCTION,
    tools=[scan_product_label],
)
```

### 7.3 `agents/chemist_agent.py`

The Chemist Agent checks for ingredient conflicts.

```python
"""
Chemist Agent — Detects ingredient conflicts between products.

WHAT THIS AGENT DOES:
1. Takes the full product shelf (all products + their ingredients)
2. Runs every product pair through the conflict rule engine
3. Returns a list of conflicts with severity and explanations

HOW THE CONFLICT DETECTION WORKS:
- First: check against the static rule engine (conflict_rules.json)
  This catches known, proven conflicts. It's fast and reliable.
- Then: use Gemini ONLY to personalize the explanation for the user's
  specific products. Gemini does NOT invent conflicts from scratch.
  This prevents hallucinated conflicts.
"""

import json
from pathlib import Path
from google import genai
from google.adk import Agent
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION

# Load conflict rules once at startup
RULES_PATH = Path(__file__).parent.parent / "data" / "conflict_rules.json"
with open(RULES_PATH) as f:
    CONFLICT_RULES = json.load(f)

client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)

CHEMIST_INSTRUCTION = """You are the Chemist Agent of Curl Chemist.

Your job: Analyze ingredient interactions between products on the user's shelf.

IMPORTANT RULES:
- You ONLY flag conflicts that match the known conflict rule engine.
- You do NOT invent new conflict types. If it's not in the rules, don't flag it.
- You personalize the explanation to mention the specific product names and ingredients.
- Severity levels: "critical" (🔴), "warning" (🟡), "info" (🟢)
"""


def _ingredient_matches_category(ingredient: dict, trigger: dict) -> str | None:
    """
    Check if an ingredient matches a conflict trigger.
    Returns the matched ingredient name or None.
    """
    ing_category = ingredient.get("category", "").lower()
    ing_name = ingredient.get("inci", ingredient.get("name", "")).lower()

    # Check by category match
    if ing_category == trigger["category"].lower():
        return ingredient["name"]

    # Check by specific ingredient name match
    for example in trigger.get("examples", []):
        if example.lower() in ing_name:
            return ingredient["name"]

    return None


def check_product_conflicts(products: list[dict]) -> list[dict]:
    """
    Run N×N conflict analysis across all products.

    This is the core conflict detection engine. For every pair of products,
    it checks every rule in the conflict database.

    Args:
        products: list of product dicts, each with an 'ingredients' list

    Returns:
        list of conflict dicts with product_a, product_b, severity, explanation, fix
    """
    conflicts = []

    for i, product_a in enumerate(products):
        for j, product_b in enumerate(products):
            if j <= i:
                continue  # Don't check a product against itself or duplicate pairs

            for rule in CONFLICT_RULES:
                # Skip rules that need conditions (handled separately)
                if "condition" in rule and "trigger_b" not in rule:
                    continue

                if "trigger_b" not in rule:
                    continue

                # Check if product_a has trigger_a and product_b has trigger_b
                for ing_a in product_a.get("ingredients", []):
                    match_a = _ingredient_matches_category(ing_a, rule["trigger_a"])
                    if not match_a:
                        continue

                    for ing_b in product_b.get("ingredients", []):
                        match_b = _ingredient_matches_category(
                            ing_b, rule["trigger_b"]
                        )
                        if not match_b:
                            continue

                        # Found a conflict!
                        conflicts.append({
                            "rule_id": rule["id"],
                            "type": rule["type"],
                            "severity": rule["severity"],
                            "product_a_id": product_a["id"],
                            "product_a_name": product_a.get("product_name", "Unknown"),
                            "product_b_id": product_b["id"],
                            "product_b_name": product_b.get("product_name", "Unknown"),
                            "ingredient_a": match_a,
                            "ingredient_b": match_b,
                            "explanation": rule["explanation"]
                                .replace("{a}", match_a)
                                .replace("{b}", match_b),
                            "fix": rule["fix"],
                        })

    return conflicts


def check_climate_conflicts(
    products: list[dict], humidity: float, uv_index: float
) -> list[dict]:
    """
    Check for climate-dependent conflicts.
    These are conflicts that only apply under certain weather conditions.
    """
    climate_conflicts = []

    for rule in CONFLICT_RULES:
        condition = rule.get("condition")
        if not condition:
            continue

        # Check humidity conditions
        should_check = False
        if condition == "humidity_above_65" and humidity > 65:
            should_check = True
        elif condition == "humidity_below_30" and humidity < 30:
            should_check = True
        elif condition == "uv_index_above_7_and_no_uv_filter" and uv_index > 7:
            should_check = True

        if not should_check:
            continue

        for product in products:
            for ingredient in product.get("ingredients", []):
                match = _ingredient_matches_category(ingredient, rule["trigger_a"])
                if match:
                    climate_conflicts.append({
                        "rule_id": rule["id"],
                        "type": rule["type"],
                        "severity": rule["severity"],
                        "product_name": product.get("product_name", "Unknown"),
                        "product_id": product["id"],
                        "ingredient": match,
                        "condition": condition,
                        "explanation": rule["explanation"].replace("{a}", match),
                        "fix": rule["fix"],
                    })

    return climate_conflicts


# Define the ADK agent
chemist_agent = Agent(
    name="chemist",
    model=GEMINI_MODEL,
    instruction=CHEMIST_INSTRUCTION,
    tools=[check_product_conflicts, check_climate_conflicts],
)
```

### 7.4 `agents/climate_agent.py`

The Climate Agent fetches weather and generates routines.

```python
"""
Climate Agent — Fetches weather data and generates daily routines.

WHAT THIS AGENT DOES:
1. Fetches tomorrow's weather forecast for Cairo from Open-Meteo (free API)
2. Analyzes how the weather affects hair care (humidity, UV, temperature)
3. Generates a personalized routine using the user's product shelf
4. The routine accounts for weather conditions and known conflicts

WHY OPEN-METEO:
- Free, no API key required
- Reliable forecast data
- Has humidity, UV index, temperature, and dew point
- Must attribute in README (it's open source)
"""

import httpx
from google import genai
from google.adk import Agent
from config import (
    GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION,
    CAIRO_LAT, CAIRO_LON, WEATHER_API_URL,
)

client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)

CLIMATE_INSTRUCTION = """You are the Climate Agent of Curl Chemist.

Your job: Generate personalized daily hair care routines based on weather conditions
and the user's product shelf.

You consider:
- Humidity: affects humectant behavior (>65% = skip glycerin, <30% = seal with oils)
- UV Index: above 7 = recommend UV protection or physical cover
- Temperature: hot = lighter products, cold = heavier creams
- Dew point: the true measure of moisture in air (more reliable than humidity %)

You generate step-by-step routines with:
- Specific product names from the user's shelf
- Application amounts (e.g., "quarter-sized amount")
- Wait times between steps (e.g., "let sit 5 minutes under a cap")
- Technique notes (e.g., "scrunch, don't rub")

IMPORTANT: Never recommend products NOT on the user's shelf.
Only work with what they have.
"""


async def fetch_cairo_weather() -> dict:
    """
    Fetch tomorrow's weather forecast for Cairo.

    Returns dict with: humidity, uv_index, temperature, dew_point,
    wind_speed, and a human-readable summary.
    """
    params = {
        "latitude": CAIRO_LAT,
        "longitude": CAIRO_LON,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "relative_humidity_2m_mean",
            "uv_index_max",
            "precipitation_probability_max",
            "wind_speed_10m_max",
        ],
        "hourly": ["dew_point_2m"],
        "timezone": "Africa/Cairo",
        "forecast_days": 2,  # Today + tomorrow
    }

    async with httpx.AsyncClient() as http_client:
        response = await http_client.get(WEATHER_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

    # Extract tomorrow's data (index 1)
    daily = data.get("daily", {})
    tomorrow_idx = 1 if len(daily.get("temperature_2m_max", [])) > 1 else 0

    # Average dew point for tomorrow's daytime hours (8AM-8PM)
    hourly_dew = data.get("hourly", {}).get("dew_point_2m", [])
    # Tomorrow's hours are indices 24-47 if we got 2 days of hourly data
    tomorrow_dew_hours = hourly_dew[24:48] if len(hourly_dew) > 24 else hourly_dew[:24]
    daytime_dew = tomorrow_dew_hours[8:20] if len(tomorrow_dew_hours) > 20 else tomorrow_dew_hours
    avg_dew_point = sum(daytime_dew) / len(daytime_dew) if daytime_dew else 20.0

    weather = {
        "temperature_max": daily.get("temperature_2m_max", [30])[tomorrow_idx],
        "temperature_min": daily.get("temperature_2m_min", [20])[tomorrow_idx],
        "humidity": daily.get("relative_humidity_2m_mean", [50])[tomorrow_idx],
        "uv_index": daily.get("uv_index_max", [5])[tomorrow_idx],
        "precipitation_probability": daily.get("precipitation_probability_max", [0])[tomorrow_idx],
        "wind_speed": daily.get("wind_speed_10m_max", [10])[tomorrow_idx],
        "dew_point": round(avg_dew_point, 1),
    }

    return weather


async def generate_routine(products: list[dict], weather: dict, profile: dict) -> dict:
    """
    Generate a personalized daily routine using Gemini.

    Args:
        products: user's product shelf with ingredients
        weather: tomorrow's weather data
        profile: user's hair profile (type, porosity, goals)

    Returns:
        dict with steps, weather_summary, and climate_notes
    """
    from google.genai import types

    product_summaries = []
    for p in products:
        ing_names = [i["name"] for i in p.get("ingredients", [])[:5]]
        product_summaries.append(
            f"- {p.get('product_name', 'Unknown')} ({p.get('product_type', 'unknown')}): "
            f"key ingredients: {', '.join(ing_names)}"
        )

    prompt = f"""Generate a hair care routine for tomorrow based on this data.

WEATHER TOMORROW:
- Temperature: {weather['temperature_max']}°C high / {weather['temperature_min']}°C low
- Humidity: {weather['humidity']}%
- UV Index: {weather['uv_index']}
- Dew Point: {weather['dew_point']}°C
- Wind: {weather['wind_speed']} km/h
- Rain chance: {weather['precipitation_probability']}%

USER'S HAIR PROFILE:
- Hair type: {profile.get('hair_type', 'wavy')}
- Porosity: {profile.get('porosity', 'medium')}
- Thickness: {profile.get('thickness', 'medium')}
- Current goals: {profile.get('goals', ['reduce frizz', 'improve definition'])}

AVAILABLE PRODUCTS:
{chr(10).join(product_summaries)}

RULES:
- Only recommend products from the list above
- If humidity > 65%: avoid glycerin and humectant-heavy products
- If humidity < 30%: seal moisture with oils/butters
- If UV > 7: recommend UV protection or physical cover
- Application order: cleanser → treatment → leave-in → styler → sealant
- Include specific amounts and technique notes

Return a JSON object with:
- "summary": one-line weather-based summary (e.g., "High humidity day — anti-frizz protocol")
- "is_wash_day": true/false recommendation
- "steps": array of objects with "order", "action", "product_name", "amount", "technique", "wait_minutes"
- "climate_notes": array of strings explaining why specific choices were made
"""

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Part.from_text(prompt)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    import json
    return json.loads(response.text)


# Define the ADK agent
climate_agent = Agent(
    name="climate",
    model=GEMINI_MODEL,
    instruction=CLIMATE_INSTRUCTION,
    tools=[fetch_cairo_weather, generate_routine],
)
```

### 7.5 `agents/profiler_agent.py`

The Profiler Agent analyzes hair health trends over time.

```python
"""
Profiler Agent — Analyzes hair health trends from wash day photos.

WHAT THIS AGENT DOES:
1. Takes wash day photos and analyzes them via Gemini Vision
2. Scores: frizz level, curl definition, shine, visible damage (1-10 each)
3. Correlates scores with products used + weather that day
4. Detects trends and generates insights
5. Writes findings that Pipeline 3 uses to auto-adjust routines
"""

from google import genai
from google.adk import Agent
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION

client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)

PROFILER_INSTRUCTION = """You are the Profiler Agent of Curl Chemist.

Your job: Analyze hair selfie photos and track health trends over time.

When analyzing a photo, score these attributes (1-10):
- frizz_level: 1 = no frizz, 10 = extreme frizz
- curl_definition: 1 = no definition, 10 = perfect clumps
- shine: 1 = dull/matte, 10 = healthy shine
- damage_visible: 1 = no damage, 10 = severe damage visible

Be consistent across photos. Use the full range of the scale.
"""


async def analyze_hair_photo(image_uri: str) -> dict:
    """
    Analyze a hair selfie and return health scores.

    Args:
        image_uri: Cloud Storage URI of the hair photo

    Returns:
        dict with frizz_level, curl_definition, shine, damage_visible (all 1-10)
        plus observations (free text)
    """
    from google.genai import types

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_uri(file_uri=image_uri, mime_type="image/jpeg"),
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

    import json
    return json.loads(response.text)


def compute_trends(history: list[dict]) -> dict:
    """
    Compute health trends from wash history entries.

    Takes a list of wash history entries (each with analysis scores)
    and computes whether metrics are improving, declining, or stable.

    Args:
        history: list of wash entries, each with 'analysis' containing scores

    Returns:
        dict with trend direction per metric + insights
    """
    if len(history) < 2:
        return {"status": "insufficient_data", "message": "Need at least 2 wash entries for trends"}

    metrics = ["frizz_level", "curl_definition", "shine", "damage_visible"]
    trends = {}

    for metric in metrics:
        values = [
            entry.get("analysis", {}).get(metric, 5)
            for entry in history
            if entry.get("analysis", {}).get(metric) is not None
        ]
        if len(values) < 2:
            trends[metric] = "insufficient_data"
            continue

        # Simple trend: compare first half average to second half average
        mid = len(values) // 2
        first_half = sum(values[:mid]) / mid
        second_half = sum(values[mid:]) / len(values[mid:])
        diff = second_half - first_half

        if abs(diff) < 0.5:
            trends[metric] = "stable"
        elif diff > 0:
            # For frizz and damage, increasing is BAD. For definition and shine, it's GOOD.
            if metric in ("frizz_level", "damage_visible"):
                trends[metric] = "worsening"
            else:
                trends[metric] = "improving"
        else:
            if metric in ("frizz_level", "damage_visible"):
                trends[metric] = "improving"
            else:
                trends[metric] = "declining"

    # Compute averages
    averages = {}
    for metric in metrics:
        values = [
            entry.get("analysis", {}).get(metric, 5)
            for entry in history
            if entry.get("analysis", {}).get(metric) is not None
        ]
        averages[metric] = round(sum(values) / len(values), 1) if values else 5.0

    return {
        "trends": trends,
        "averages": averages,
        "entry_count": len(history),
    }


# Define the ADK agent
profiler_agent = Agent(
    name="profiler",
    model=GEMINI_MODEL,
    instruction=PROFILER_INSTRUCTION,
    tools=[analyze_hair_photo, compute_trends],
)
```

---

## 8. Phase 3: The Pipelines

These are the autonomous background jobs that run WITHOUT user interaction.

### 8.1 `pipelines/__init__.py`

```python
"""Autonomous background pipelines for Curl Chemist."""
```

### 8.2 `pipelines/nightly_routine.py` — Pipeline 1

```python
"""
Pipeline 1: Nightly Routine Generator
Trigger: Cloud Scheduler → Pub/Sub → Cloud Run endpoint, every day at 9 PM Cairo time
Human involvement: ZERO

WHAT HAPPENS:
1. Fetch tomorrow's Cairo weather
2. Load user's product shelf from Firestore
3. Load user's hair profile from Firestore
4. Check for climate-dependent conflicts
5. Generate personalized routine via Gemini
6. Save routine to Firestore
7. Log pipeline execution

The user wakes up and the routine is already there.
"""

from datetime import datetime, timedelta, timezone
from agents.climate_agent import fetch_cairo_weather, generate_routine
from agents.chemist_agent import check_climate_conflicts
from firestore_helpers import (
    get_all_products, get_user_profile, save_routine,
    log_pipeline_event, save_conflict,
)


async def run_nightly_routine_pipeline():
    """
    Execute the nightly routine generation pipeline.

    This is called by the /pipelines/nightly endpoint when
    Cloud Scheduler fires at 9 PM.
    """
    pipeline_name = "nightly_routine"

    try:
        log_pipeline_event(pipeline_name, "Pipeline triggered by Cloud Scheduler")

        # Step 1: Fetch weather
        log_pipeline_event(pipeline_name, "Fetching tomorrow's Cairo weather...")
        weather = await fetch_cairo_weather()
        log_pipeline_event(
            pipeline_name,
            f"Weather fetched: {weather['humidity']}% humidity, "
            f"UV {weather['uv_index']}, {weather['temperature_max']}°C"
        )

        # Step 2: Load products
        products = get_all_products()
        if not products:
            log_pipeline_event(
                pipeline_name,
                "No products on shelf — skipping routine generation",
                status="warning",
            )
            return {"status": "skipped", "reason": "no_products"}

        log_pipeline_event(pipeline_name, f"Loaded {len(products)} products from shelf")

        # Step 3: Load profile
        profile = get_user_profile() or {
            "hair_type": "2B wavy",
            "porosity": "medium",
            "goals": ["reduce frizz", "improve definition"],
        }

        # Step 4: Check climate conflicts
        climate_conflicts = check_climate_conflicts(
            products, weather["humidity"], weather["uv_index"]
        )
        if climate_conflicts:
            log_pipeline_event(
                pipeline_name,
                f"Found {len(climate_conflicts)} climate-dependent conflicts",
                status="warning",
            )
            for conflict in climate_conflicts:
                save_conflict(conflict)

        # Step 5: Generate routine
        log_pipeline_event(pipeline_name, "Generating routine via Gemini...")
        routine = await generate_routine(products, weather, profile)

        # Step 6: Save routine
        # Use tomorrow's date as the document ID → idempotent
        cairo_tz = timezone(timedelta(hours=2))  # Cairo is UTC+2
        tomorrow = datetime.now(cairo_tz) + timedelta(days=1)
        date_str = tomorrow.strftime("%Y-%m-%d")

        routine_data = {
            "date": date_str,
            "weather": weather,
            "climate_conflicts": climate_conflicts,
            **routine,
        }
        save_routine(date_str, routine_data)

        log_pipeline_event(
            pipeline_name,
            f"Routine generated and saved for {date_str}",
            status="success",
        )

        return {"status": "success", "date": date_str, "routine": routine_data}

    except Exception as e:
        log_pipeline_event(pipeline_name, f"Pipeline failed: {str(e)}", status="error")
        raise
```

### 8.3 `pipelines/shelf_reanalysis.py` — Pipeline 2

```python
"""
Pipeline 2: Shelf Reanalysis Cascade
Trigger: Photo uploaded to Cloud Storage → Pub/Sub → Cloud Run endpoint
Human involvement: Snapping ONE photo, then walking away

THE CASCADE:
Photo uploaded → extract ingredients → classify → save product →
run N×N conflict check → save conflicts → if critical → regenerate routines

This is the "wow moment" for the demo video — one photo triggers
a chain of autonomous actions.
"""

from agents.scanner_agent import scan_product_label
from agents.chemist_agent import check_product_conflicts
from firestore_helpers import (
    save_product, get_all_products, save_conflict,
    get_active_conflicts, log_pipeline_event,
)


async def run_shelf_reanalysis_pipeline(image_uri: str, file_name: str):
    """
    Execute the shelf reanalysis cascade.

    Args:
        image_uri: Cloud Storage URI of the uploaded product photo
        file_name: Original filename for logging
    """
    pipeline_name = "shelf_reanalysis"

    try:
        log_pipeline_event(
            pipeline_name,
            f"Cascade triggered by upload: {file_name}"
        )

        # Step 1: Extract ingredients via Gemini Vision
        log_pipeline_event(pipeline_name, "Scanning product label with Gemini Vision...")
        product_data = await scan_product_label(image_uri)
        log_pipeline_event(
            pipeline_name,
            f"Extracted {len(product_data.get('ingredients', []))} ingredients "
            f"from {product_data.get('product_name', 'unknown product')}"
        )

        # Step 2: Mark low-confidence ingredients
        needs_review = [
            i for i in product_data.get("ingredients", [])
            if i.get("needs_review")
        ]
        if needs_review:
            log_pipeline_event(
                pipeline_name,
                f"{len(needs_review)} ingredients need manual review (low OCR confidence)",
                status="warning",
            )

        # Step 3: Save product to shelf
        product_data["photo_uri"] = image_uri
        product_id = save_product(product_data)
        product_data["id"] = product_id
        log_pipeline_event(
            pipeline_name,
            f"Product saved to shelf: {product_data.get('product_name')}"
        )

        # Step 4: Run N×N conflict analysis against ENTIRE shelf
        all_products = get_all_products()
        log_pipeline_event(
            pipeline_name,
            f"Running N×N conflict analysis across {len(all_products)} products..."
        )

        conflicts = check_product_conflicts(all_products)

        # Step 5: Save new conflicts
        # Filter to only conflicts involving the new product
        new_conflicts = [
            c for c in conflicts
            if c["product_a_id"] == product_id or c["product_b_id"] == product_id
        ]

        critical_count = 0
        for conflict in new_conflicts:
            save_conflict(conflict)
            if conflict["severity"] == "critical":
                critical_count += 1

        if new_conflicts:
            log_pipeline_event(
                pipeline_name,
                f"Found {len(new_conflicts)} conflicts ({critical_count} critical) "
                f"involving {product_data.get('product_name')}",
                status="warning" if critical_count == 0 else "error",
            )
        else:
            log_pipeline_event(
                pipeline_name,
                f"No conflicts found — {product_data.get('product_name')} is compatible with your shelf!",
                status="success",
            )

        # Step 6: If critical conflicts found, trigger routine regeneration
        if critical_count > 0:
            log_pipeline_event(
                pipeline_name,
                "Critical conflicts detected — triggering routine regeneration...",
                status="error",
            )
            # Import here to avoid circular imports
            from pipelines.nightly_routine import run_nightly_routine_pipeline
            await run_nightly_routine_pipeline()
            log_pipeline_event(
                pipeline_name,
                "Routines regenerated to account for new conflicts",
                status="success",
            )

        log_pipeline_event(
            pipeline_name,
            f"Shelf reanalysis cascade complete for {product_data.get('product_name')}",
            status="success",
        )

        return {
            "status": "success",
            "product": product_data,
            "conflicts_found": len(new_conflicts),
            "critical_conflicts": critical_count,
        }

    except Exception as e:
        log_pipeline_event(pipeline_name, f"Pipeline failed: {str(e)}", status="error")
        raise
```

### 8.4 `pipelines/weekly_health.py` — Pipeline 3

```python
"""
Pipeline 3: Weekly Health Analyzer
Trigger: Cloud Scheduler → Pub/Sub → Cloud Run endpoint, every Sunday at 8 PM
Human involvement: ZERO (uses wash day data already collected)

WHAT HAPPENS:
1. Pull all wash day entries from the past 7 days
2. Compute health trends (frizz, definition, shine, damage)
3. Correlate with products used and weather conditions
4. Generate insights via Gemini
5. Auto-adjust the adaptive profile (learned preferences)
6. Save weekly report to Firestore
"""

from google import genai
from google.genai import types
from config import GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION
from agents.profiler_agent import compute_trends
from firestore_helpers import (
    get_recent_wash_history, save_weekly_report,
    get_user_profile, save_user_profile,
    log_pipeline_event,
)
from datetime import datetime, timezone

client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)


async def run_weekly_health_pipeline():
    """Execute the weekly hair health analysis pipeline."""
    pipeline_name = "weekly_health"

    try:
        log_pipeline_event(pipeline_name, "Weekly health analysis triggered")

        # Step 1: Get recent wash history
        history = get_recent_wash_history(days=7)
        if len(history) < 1:
            log_pipeline_event(
                pipeline_name,
                "No wash entries this week — skipping analysis",
                status="warning",
            )
            return {"status": "skipped", "reason": "no_data"}

        log_pipeline_event(pipeline_name, f"Analyzing {len(history)} wash entries from this week")

        # Step 2: Compute trends
        trend_data = compute_trends(history)
        log_pipeline_event(
            pipeline_name,
            f"Trends computed: {trend_data.get('trends', {})}"
        )

        # Step 3: Generate insights via Gemini
        log_pipeline_event(pipeline_name, "Generating insights via Gemini...")

        # Build context for Gemini
        history_summary = []
        for entry in history:
            analysis = entry.get("analysis", {})
            weather = entry.get("weather_that_day", {})
            products = entry.get("products_used", [])
            history_summary.append(
                f"Date: {entry.get('date', 'unknown')}, "
                f"Frizz: {analysis.get('frizz_level', '?')}, "
                f"Definition: {analysis.get('curl_definition', '?')}, "
                f"Humidity: {weather.get('humidity', '?')}%, "
                f"Products: {', '.join(products) if products else 'unknown'}"
            )

        prompt = f"""Analyze this week's hair health data and generate actionable insights.

WEEKLY DATA:
{chr(10).join(history_summary)}

COMPUTED TRENDS:
{trend_data}

Generate 3-5 specific, actionable insights. Examples:
- "Curl definition improved on days when you used [product X] but not [product Y]"
- "Frizz was worst on high-humidity days when you used glycerin-based products"
- "Your best hair day was [date] — you used [products] in [weather conditions]"

Also suggest 1-2 routine adjustments based on the data.

Return JSON with keys: "insights" (array of strings), "routine_adjustments" (array of strings),
"best_day" (date string), "worst_day" (date string).
"""

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Part.from_text(prompt)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

        import json
        insights = json.loads(response.text)

        # Step 4: Update adaptive profile with learned preferences
        profile = get_user_profile() or {}
        adaptive = profile.get("adaptive_profile", {})

        # Store this week's adjustments in the long-term profile
        adaptive["last_weekly_analysis"] = datetime.now(timezone.utc).isoformat()
        adaptive["latest_trends"] = trend_data.get("trends", {})
        adaptive["routine_adjustments"] = insights.get("routine_adjustments", [])

        save_user_profile({"adaptive_profile": adaptive})

        log_pipeline_event(
            pipeline_name,
            "Adaptive profile updated with this week's learnings"
        )

        # Step 5: Save weekly report
        now = datetime.now(timezone.utc)
        week_str = now.strftime("%Y-W%W")

        report = {
            "period": f"Week of {now.strftime('%B %d, %Y')}",
            "entry_count": len(history),
            "trends": trend_data,
            "insights": insights.get("insights", []),
            "routine_adjustments": insights.get("routine_adjustments", []),
            "best_day": insights.get("best_day"),
            "worst_day": insights.get("worst_day"),
        }

        save_weekly_report(week_str, report)

        log_pipeline_event(
            pipeline_name,
            f"Weekly report saved: {len(insights.get('insights', []))} insights generated",
            status="success",
        )

        return {"status": "success", "report": report}

    except Exception as e:
        log_pipeline_event(pipeline_name, f"Pipeline failed: {str(e)}", status="error")
        raise
```

---

## 9. Phase 4: The Main App + Dashboard

### 9.1 `main.py` — The Single Entry Point

This is the FastAPI application that Cloud Run runs. It handles:
- Dashboard serving (the web UI)
- Pipeline trigger endpoints (hit by Cloud Scheduler / Pub/Sub)
- API endpoints (for the dashboard to fetch data)

```python
"""
Curl Chemist — Main Application

This is the single entry point for everything:
1. Serves the dashboard web UI
2. Exposes pipeline trigger endpoints (called by Cloud Scheduler + Pub/Sub)
3. Provides API endpoints for the dashboard to fetch live data

Cloud Run runs this. Cloud Scheduler hits the pipeline endpoints.
The dashboard JavaScript calls the API endpoints.
"""

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
```

### 9.2 The Dashboard

The dashboard is a single HTML page with JavaScript that polls the API. It's designed to look like a **mission control system**, NOT a chatbot.

Create `dashboard/templates/index.html`, `dashboard/static/style.css`, and `dashboard/static/app.js`. These are large files — **build the HTML/CSS/JS with AI assistance** (Cursor, Antigravity, etc.) using the dashboard wireframe from the design doc as the reference. Here's what the dashboard must show:

**Required panels (top to bottom):**

1. **System Status** — 4 pipeline indicators (🟢 running, 🟡 idle, 🔴 error) with last run timestamps
2. **Today's Routine Card** — weather conditions + step-by-step routine (fetched from `/api/routine`)
3. **Active Alerts** — conflict alerts with severity icons (from `/api/conflicts`)
4. **Product Shelf** — grid of scanned products with photo thumbnails + conflict badges + "Scan New Product" upload button
5. **Compatibility Matrix** — NxN grid showing which products are compatible (✅/🔴/🟡)
6. **Health Timeline** — sparkline charts of frizz, definition, shine, damage over time
7. **Pipeline Execution Log** — scrolling log of recent pipeline events (from `/api/logs`)
8. **Chat Panel** — small, collapsible panel in the bottom corner (for onboarding only)

> [!TIP]
> **Build the dashboard LAST.** Get all 3 pipelines working first, then build the dashboard around the data they produce. A working pipeline with an ugly dashboard beats a beautiful dashboard with broken pipelines.

---

## 10. Phase 5: Deployment

### 10.1 `Dockerfile`

```dockerfile
# Use Python 3.11 slim image (small, fast to build)
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first (Docker caches this layer if requirements don't change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Cloud Run sets the PORT environment variable (usually 8080)
# Uvicorn is the ASGI server that runs FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 10.2 `.dockerignore`

```
.env
__pycache__
*.pyc
.git
.gitignore
README.md
```

### 10.3 Deploy to Cloud Run

```powershell
# Step 1: Build and push the Docker image to Google Artifact Registry
# (Cloud Build does this for you — no need to build locally)

# First, create an Artifact Registry repository (one-time)
gcloud artifacts repositories create curl-chemist-repo `
  --repository-format=docker `
  --location=europe-west1

# Step 2: Build and deploy to Cloud Run in ONE command
# This builds the Docker image, pushes it, and deploys to Cloud Run
gcloud run deploy curl-chemist `
  --source=. `
  --region=europe-west1 `
  --service-account=curl-chemist-sa@curl-chemist-rawan.iam.gserviceaccount.com `
  --allow-unauthenticated `
  --set-env-vars="GCP_PROJECT_ID=curl-chemist-rawan,GCP_REGION=europe-west1,GEMINI_MODEL=gemini-2.5-flash,PHOTOS_BUCKET=curl-chemist-rawan-photos" `
  --memory=1Gi `
  --timeout=300
```

After deployment, Cloud Run gives you a URL like:
```
https://curl-chemist-XXXXXXXX-ew.a.run.app
```

**Save this URL** — you need it for Cloud Scheduler, the Devpost submission, and the demo video.

---

## 11. Phase 6: Cloud Scheduler + Pub/Sub Wiring

This connects everything together so pipelines run automatically.

### 11.1 Create Pub/Sub push subscriptions

Push subscriptions tell Pub/Sub to forward messages to your Cloud Run endpoints.

```powershell
# Replace YOUR_CLOUD_RUN_URL with the URL from the deploy step

# Subscription for nightly routine trigger
gcloud pubsub subscriptions create nightly-routine-sub `
  --topic=nightly-routine-trigger `
  --push-endpoint=YOUR_CLOUD_RUN_URL/pipelines/nightly `
  --push-auth-service-account=curl-chemist-sa@curl-chemist-rawan.iam.gserviceaccount.com

# Subscription for shelf reanalysis (triggered by Cloud Storage uploads)
gcloud pubsub subscriptions create shelf-reanalysis-sub `
  --topic=shelf-updated `
  --push-endpoint=YOUR_CLOUD_RUN_URL/pipelines/shelf-reanalysis `
  --push-auth-service-account=curl-chemist-sa@curl-chemist-rawan.iam.gserviceaccount.com

# Subscription for weekly health analysis
gcloud pubsub subscriptions create weekly-health-sub `
  --topic=weekly-health-trigger `
  --push-endpoint=YOUR_CLOUD_RUN_URL/pipelines/weekly-health `
  --push-auth-service-account=curl-chemist-sa@curl-chemist-rawan.iam.gserviceaccount.com
```

### 11.2 Create Cloud Scheduler jobs

These are your cron jobs — they fire on schedule and publish to Pub/Sub.

```powershell
# Pipeline 1: Nightly routine at 9 PM Cairo time every day
gcloud scheduler jobs create pubsub nightly-routine-job `
  --schedule="0 21 * * *" `
  --time-zone="Africa/Cairo" `
  --topic=nightly-routine-trigger `
  --message-body="{\"trigger\": \"scheduled\"}" `
  --location=europe-west1

# Pipeline 3: Weekly health analysis every Sunday at 8 PM Cairo time
gcloud scheduler jobs create pubsub weekly-health-job `
  --schedule="0 20 * * 0" `
  --time-zone="Africa/Cairo" `
  --topic=weekly-health-trigger `
  --message-body="{\"trigger\": \"scheduled\"}" `
  --location=europe-west1
```

> [!NOTE]
> **Cron syntax explained:**
> - `0 21 * * *` = at minute 0 of hour 21 (9 PM), every day of month, every month, every day of week
> - `0 20 * * 0` = at 8 PM, every Sunday (0 = Sunday)

### 11.3 Pipeline 2 is already wired!

Remember in Step 7 of GCP setup, we created a Cloud Storage notification on the photos bucket. When a file is uploaded:
```
Cloud Storage upload → publishes to "shelf-updated" topic →
Pub/Sub pushes to /pipelines/shelf-reanalysis endpoint →
Pipeline 2 runs automatically
```

No extra setup needed. This is the cascade trigger.

---

## 12. Phase 7: Testing Everything

### 12.1 Test locally first

```powershell
# Set up a virtual environment
python -m venv venv
.\venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt

# Set up local Google credentials
# This lets your code access Firestore, Cloud Storage, etc. from your machine
gcloud auth application-default login

# Create a .env file from the template
copy .env.example .env
# Edit .env with your actual values

# Run the app locally
uvicorn main:app --reload --port 8080
```

Open `http://localhost:8080` — you should see the dashboard.

### 12.2 Test Pipeline 1 manually

```powershell
# Call the nightly routine endpoint directly
curl -X POST http://localhost:8080/pipelines/nightly
```

Check Firestore in the console: `users/rawan/routines/{today's date}` should have a new document.

### 12.3 Test Pipeline 2 manually

```powershell
# Upload a product photo to Cloud Storage
gcloud storage cp path/to/product-photo.jpg gs://curl-chemist-rawan-photos/products/test-product.jpg
```

This should trigger the cascade. Watch the pipeline logs in the dashboard or check Firestore.

Or test directly via the API:

```powershell
# Call the endpoint directly (simulating Pub/Sub)
curl -X POST http://localhost:8080/pipelines/shelf-reanalysis `
  -H "Content-Type: application/json" `
  -d "{\"bucket\": \"curl-chemist-rawan-photos\", \"name\": \"products/test-product.jpg\"}"
```

### 12.4 Test Pipeline 3 manually

First, seed some fake wash history data so Pipeline 3 has something to analyze:

```python
# Run this in a Python shell or as a one-off script
from firestore_helpers import save_wash_entry
from datetime import datetime, timedelta, timezone

# Seed 5 days of wash history
for i in range(5):
    save_wash_entry({
        "date": (datetime.now(timezone.utc) - timedelta(days=i)).isoformat(),
        "analysis": {
            "frizz_level": 7 - i,  # Improving trend
            "curl_definition": 3 + i,  # Improving trend
            "shine": 4 + i,
            "damage_visible": 3,
        },
        "weather_that_day": {"humidity": 55 + (i * 5)},
        "products_used": ["Eva Clinic Mask", "Bless Mega Hold Gel"],
    })
```

Then trigger Pipeline 3:
```powershell
curl -X POST http://localhost:8080/pipelines/weekly-health
```

### 12.5 Test on Cloud Run

After deployment, test the same endpoints using your Cloud Run URL:

```powershell
curl -X POST https://curl-chemist-XXXXXXXX-ew.a.run.app/pipelines/nightly
```

### 12.6 Test the scheduled triggers

You can manually trigger a Cloud Scheduler job to verify the full chain works:

```powershell
gcloud scheduler jobs run nightly-routine-job --location=europe-west1
```

---

## 13. Phase 8: Demo, Docs, Ship

### 13.1 Architecture Diagram

Use draw.io (https://app.diagrams.net) or Excalidraw (https://excalidraw.com) to create a clean version of the architecture from the design doc. Export as PNG, add to README.

### 13.2 README.md structure

```markdown
# ⚗️ Curl Chemist — Autonomous Personal Care Chemistry Engine

[One-line description]

## 🎯 The Problem (BYOF)
[Your personal friction story — 2-3 sentences]

## ⚙️ Architecture
![Architecture Diagram](./architecture.png)

## 🛠️ Tech Stack
[Table: technology + what it does]

## 🚀 Setup & Deployment

### Prerequisites
- Python 3.11+, gcloud CLI, Docker

### Local Development
[Step-by-step: clone, install, env vars, run]

### Deploy to Google Cloud
[Step-by-step: gcloud commands]

### Manual Pipeline Triggers
[How to trigger each pipeline for testing]

## 📊 Firestore Schema
[Document structure]

## 🔒 Security
- Pub/Sub push subscriptions use OIDC authentication
- Firestore security rules lock data by userId
- Agent tools are scoped (tool isolation table)

## 🌤️ Data Sources
- Weather: [Open-Meteo](https://open-meteo.com/) (free, open-source)
- Ingredient knowledge: Curated conflict rule engine (15+ rules)

## 📝 License
[Your choice — MIT is fine for hackathons]
```

### 13.3 Blog Post (dev.to)

Write and publish on dev.to. Must include:
- The phrase: "I created this project for the All Things Agentic Hackathon"
- Your BYOF story
- Architecture overview
- What you learned

### 13.4 Social Post

Post on LinkedIn with:
- A GIF or screenshot of the dashboard
- `#AllThingsAgenticHackathon` (no space)
- Brief description of what you built

### 13.5 Devpost Submission

Fill out every field:
- **Category:** Taskmaster
- **Hosted URL:** Your Cloud Run URL
- **Repo URL:** GitHub link
- **Video:** YouTube link (public, ≤4 min, English)
- **Text description:** Use the one from the sprint plan (Section 7)

---

## 14. Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `403 Forbidden` on Vertex AI calls | Service account doesn't have `aiplatform.user` role | Re-run the IAM command from Step 9 |
| Pub/Sub messages not reaching Cloud Run | Push subscription URL is wrong, or missing auth | Check subscription config: `gcloud pubsub subscriptions describe shelf-reanalysis-sub` |
| Firestore writes fail with `Permission denied` | Service account needs `datastore.user` role | Re-run IAM command |
| Cloud Scheduler job shows as `FAILED` | The Cloud Run endpoint returned a non-2xx response | Check Cloud Run logs: `gcloud run services logs read curl-chemist --region=europe-west1` |
| Gemini returns garbled JSON | Temperature too high, or the prompt is ambiguous | Lower temperature to 0.1, add "Return valid JSON only" to prompt |
| Cloud Storage upload doesn't trigger pipeline | Notification not set up on the bucket | Re-run: `gcloud storage buckets notifications list gs://curl-chemist-rawan-photos` |
| Cloud Run cold starts are slow (>10s) | Container needs to warm up Gemini client | Set `--min-instances=1` on Cloud Run (costs more but eliminates cold starts) |
| Dashboard shows empty data | Firestore has no data yet | Seed fake data (Section 12.4) or trigger Pipeline 1 manually |
| `ModuleNotFoundError` in Cloud Run | Missing package in requirements.txt | Add the package, rebuild, redeploy |

### Reading Cloud Run logs

```powershell
# Live-tail the logs (useful during demo recording)
gcloud run services logs tail curl-chemist --region=europe-west1

# Read recent logs
gcloud run services logs read curl-chemist --region=europe-west1 --limit=50
```

### Checking Firestore data

Go to: `https://console.cloud.google.com/firestore/databases/-default-/data`

Navigate to: `users` → `rawan` → and explore the subcollections (products, routines, conflicts, pipeline_logs, etc.)

---

> [!IMPORTANT]
> **The #1 mistake hackathon participants make:** They spend 90% of time coding and 10% on the demo video. Flip it to 70/30. A polished 4-minute video showing a working system beats a complex system that the judges can't see working. Get Pipelines 1-3 working by end of Day 2, spend ALL of Day 3 on the demo, docs, and submission.
