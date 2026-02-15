"""Send a minimal simulated Telegram update to local webhook for testing.

Usage:
  python scripts/local_test_update.py

Requires `BOT_TOKEN` and optionally `WEBHOOK_PATH` and `PORT` env vars.
"""
import os
import requests
import json
from dotenv import load_dotenv

# load .env if present
load_dotenv()


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN env var to simulate chat_id.")
        return

    port = int(os.getenv("PORT", "8000"))
    path = os.getenv("WEBHOOK_PATH", "webhook")
    url = f"http://127.0.0.1:{port}/{path}"

    update = {
        "update_id": 10000,
        "message": {
            "message_id": 1,
            "from": {"id": 12345, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 12345, "type": "private"},
            "date": 1600000000,
            "text": "Test message from local_test_update",
        },
    }

    r = requests.post(url, json=update)
    try:
        print(r.status_code, r.json())
    except Exception:
        print(r.status_code, r.text)


if __name__ == "__main__":
    main()
