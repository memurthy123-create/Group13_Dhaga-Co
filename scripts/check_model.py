"""One synthetic Model A request with direct error output. No OpenAI call."""
from pathlib import Path
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from dhaga.models import ModelGateway
from dhaga.errors import ModelFailure, capture_error
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["DEBUG_ERRORS"] = "true"
g = ModelGateway()
raw = {"text": "The shirt arrived torn. I want to return it."}
try:
    g.validate_provider_a()
    print("Provider:", g.provider_a, "Model:", g.model_a)
    result = g._jev_decide("returns", raw) if g.provider_a == "typesafe" else g._chat_decide("returns", raw)
    print("SUCCESS:", result.primary_reason)
except (ModelFailure, ValueError) as exc:
    capture_error(exc, "Single-record connection check")
    sys.exit(1)
