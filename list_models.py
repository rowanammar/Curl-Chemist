"""
List all models available to your GEMMA_API_KEY / GEMINI_API_KEY via the
Generative Language API (v1beta) — the same endpoint advisor_agent.py hits
when it does genai.Client(api_key=...).

Usage:
    python list_models.py
"""

import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMMA_API_KEY") or os.getenv("GEMINI_API_KEY")

if not api_key:
    raise SystemExit(
        "No GEMMA_API_KEY or GEMINI_API_KEY found in your environment. "
        "Set one in .env before running this."
    )

client = genai.Client(api_key=api_key)

print(f"Using API key: {api_key[:6]}...{api_key[-4:]}\n")
print("Models that support generateContent:\n")

for model in client.models.list():
    # actions/supported_actions varies by SDK version — check both attribute names defensively
    supported = getattr(model, "supported_actions", None) or getattr(
        model, "supported_generation_methods", None
    ) or []

    if "generateContent" in supported:
        name = model.name  # usually like "models/gemma-4-4b-it"
        print(f"  {name}")

print("\nAll models (including ones that don't support generateContent):\n")
for model in client.models.list():
    print(f"  {model.name}")