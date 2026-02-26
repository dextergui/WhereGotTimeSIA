import os
import json
import base64
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Required
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TRUSTED_CHAT_IDS = set(map(int, os.getenv("TRUSTED_IDS").split(",")))
SHEET_ID = os.getenv("SHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1")

# The service account JSON for Google APIs (base64 or raw JSON string)
GOOGLE_CREDS_B64 = os.getenv("GOOGLE_CREDS_B64")

# Webhook path (set on Render as: https://<service>.onrender.com/<WEBHOOK_PATH>)
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "webhook")

INSTRUCTION_TEXT = (
    "Send a timesheet image (photo or file).\n\n"
    "After parsing, I will ask whether to push to Google Sheets."
)

def ensure_google_creds_file() -> str | None:
    """If GOOGLE_CREDS_B64 provided, decode and write to temp file and set env var."""
    if not GOOGLE_CREDS_B64:
        return None
    try:
        # detect if it's base64
        maybe_json = None
        try:
            decoded = base64.b64decode(GOOGLE_CREDS_B64).decode("utf-8")
            maybe_json = json.loads(decoded)
        except Exception:
            # maybe it's raw JSON
            try:
                maybe_json = json.loads(GOOGLE_CREDS_B64)
            except Exception:
                maybe_json = None

        if maybe_json is None:
            return None

        creds_path = BASE_DIR.parent / "google_creds.json"
        creds_path.write_text(json.dumps(maybe_json))
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)
        return str(creds_path)
    except Exception:
        return None


# Ensure credentials set at import time if provided
ensure_google_creds_file()
