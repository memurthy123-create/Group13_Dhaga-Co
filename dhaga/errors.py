"""Provider diagnostics and optional error output with secrets redacted."""
import os
import re
import sys
import traceback


def debug_enabled():
    return os.getenv("DEBUG_ERRORS", "false").lower() in ("true", "1", "yes")


def capture_error(exc, context):
    if not debug_enabled():
        return ""
    output = context + "\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    response = getattr(exc, "response", None)
    if response is not None:
        output += f"\nHTTP status: {response.status_code}\nProvider response body:\n{response.text}"
    # Do not print request headers or local variables. Also scrub known secrets
    # in case a provider echoes one in its error response.
    for name, value in os.environ.items():
        if value and ("API_KEY" in name or name in ("APP_PASSWORD", "SUPABASE_SERVICE_ROLE_KEY")):
            output = output.replace(value, "[REDACTED]")
    output = re.sub(r"(?i)(Bearer\s+)[^\s\"']+", r"\1[REDACTED]", output)
    output = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", output)
    print(output, file=sys.stderr, flush=True)
    return output

class ModelFailure(RuntimeError):
    def __init__(self, message, stop_batch=False):
        super().__init__(message)
        self.stop_batch = stop_batch


def http_failure(provider, status):
    hints = {
        400: "Provider rejected the request. Check the request schema and model ID.",
        401: "Authentication rejected. Check the correct provider API key in .env, then restart Streamlit.",
        402: "Payment or credit required. Check the provider billing dashboard.",
        403: "Access denied. Check account permissions and model access.",
        404: "Endpoint or model not found. Check the configured model ID and provider endpoint.",
        422: "Request validation failed. The provider rejected the request format or model ID.",
        429: "Rate or quota limit reached. Check account limits and credit before retrying.",
        529: "Provider is overloaded. Retry later.",
    }
    return ModelFailure(f"{provider} HTTP {status}: " + hints.get(status, "Provider request failed. Check its service status and retry later."),
                        stop_batch=status in (400, 401, 402, 403, 404, 422))
