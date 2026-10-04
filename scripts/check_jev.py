"""Run one synthetic Jev decision; prints no API keys or raw provider errors."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from dhaga.models import ModelGateway
from dhaga.errors import ModelFailure
import os
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
if not os.getenv("TYPESAFE_API_KEY"):
    print("Missing TYPESAFE_API_KEY in .env. Use the TypeSafe key, not an OpenAI key.")
    sys.exit(1)
g = ModelGateway()  # Jev-only check; no OpenAI request or client needed.
try:
    result = g._jev_decide("returns", {"text": "The shirt arrived torn. I want to return it."})
    print("Jev connection and response validation succeeded.")
    print("Selected reason:", result.primary_reason)
    print("Resolved model:", g.calls[-1].get("resolved_model", "unknown"))
except ModelFailure as exc:
    print(str(exc))
    sys.exit(1)
