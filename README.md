# Curl Chemist 🧪➰

**An Autonomous Hair Care Agent that goes beyond the chat loop to build routines, detect chemical conflicts, and manage your schedule.**

![Architecture Diagram](./architecture_revised.png)

## 🏆 Submission for the #AllThingsAgentic Hackathon
**Category:** Taskmaster
**Theme:** Bring Your Own Friction (BYOF)

Curl Chemist solves the incredibly frustrating friction of curly hair care: ingredient conflicts, weather-dependent product reactions, and complex routines. Instead of a standard chatbot, Curl Chemist is a background **Autonomous ReAct Agent** that intercepts multi-step workflows.

Triggered nightly by Cloud Scheduler, the agent autonomously checks tomorrow's weather, analyzes the chemical composition of the products on your shelf, detects climate conflicts (e.g., glycerin in high humidity), generates a personalized routine, and even schedules calendar blocks for deep conditioning days.

---

## 🏗️ Architectural Discipline & Security

This project was built with strict engineering standards and enterprise-grade patterns:

- **True ReAct Orchestrator (`orchestrator.py`):** The core pipeline does not use rigid Python scripts. It feeds a goal and a tool registry to Gemini. The LLM sequences the tool calls, analyzes results, and features a **self-healing try/catch loop** that feeds tool execution errors back to the agent for auto-correction.
- **Model Armor & PII Redaction (`input_sanitizer.py`):** Utilizes **Gemma** to scan all incoming inputs for prompt injection attacks before they reach the main orchestrator. It also strips PII (emails/phone numbers) and truncates payloads to prevent tool poisoning.
- **Zero-Trust Agent Gateway (`main.py`):** Custom FastAPI middleware that validates JWTs for user routes and OIDC tokens for internal Cloud Scheduler/PubSub pipeline triggers.
- **Deterministic + Generative Chemist (`chemist_agent.py`):** Uses a deterministic JSON rule engine for chemical conflict detection to guarantee zero hallucinations, and then uses Gemini strictly to intelligently consolidate and personalize the explanation.

---

## ⚙️ Tech Stack

- **Models:** Gemini 3.5 Flash (Core Agent), Gemma (Model Armor/Prompt Injection Detection)
- **Frameworks:** GenAI SDK (`google.genai`), FastAPI, Jinja2
- **Google Cloud Platform:** 
  - **Compute:** Cloud Run (Serverless Backend)
  - **Database:** Firestore (Memory Bank & State Management)
  - **Storage:** Cloud Storage (Hair profile photos, product scans)
  - **CI/CD:** Cloud Build
  - **Async Triggers:** Cloud Scheduler & Pub/Sub
  - **Security:** Secret Manager

---

## 🚀 Spin-Up Instructions (Reproducibility)

Follow these steps to run Curl Chemist locally or deploy it to Google Cloud.

### 1. Prerequisites
- Python 3.11+
- Google Cloud CLI (`gcloud`) installed and authenticated
- A Google Cloud Project with Billing Enabled
- Firestore in Native Mode enabled

### 2. Environment Variables
Create a `.env` file in the root directory:
```env
IS_DEV=true
GCP_PROJECT_ID=your-gcp-project-id
GCP_REGION=europe-west2
GEMINI_API_KEY=your-gemini-api-key # Optional if using Vertex AI directly
GEMMA_API_KEY=your-gemma-api-key   # For prompt injection guardrails
PHOTOS_BUCKET=your-cloud-storage-bucket-name
JWT_SECRET=your-secure-random-jwt-secret
```

### 3. Running Locally
1. Clone the repository and navigate to the root folder.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   # On Windows: venv\Scripts\activate
   # On Mac/Linux: source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Authenticate with Google Cloud (for Firestore/GCS access):
   ```bash
   gcloud auth application-default login
   ```
4. Start the FastAPI server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
5. Open `http://localhost:8000` in your browser.

### 4. Cloud Deployment (Cloud Run)
This project includes a `Dockerfile` and `cloudbuild.yaml` for seamless deployment.

1. Create a Cloud Storage bucket for photos:
   ```bash
   gcloud storage buckets create gs://YOUR_BUCKET_NAME --location=europe-west2
   ```
2. Store your secrets in Google Secret Manager (matching the names in `cloudbuild.yaml`):
   - `jwt-secret`
   - `gemma-api-key`
3. Deploy using Cloud Build:
   ```bash
   gcloud builds submit --config cloudbuild.yaml .
   ```
4. Access the provided `.run.app` URL returned by Cloud Build.

---
*Built with ❤️ for the Google #AllThingsAgentic Hackathon.*