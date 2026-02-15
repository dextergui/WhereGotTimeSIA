"""Small helper to call Telegram's setWebhook for your bot.

Usage:
  python scripts/set_webhook.py https://your-service.onrender.com

It will use WEBHOOK_PATH from env or default `webhook`.
"""
import os
import sys
import requests
from dotenv import load_dotenv

# load .env if present
load_dotenv()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/set_webhook.py <base_url>")
        sys.exit(1)

    base = sys.argv[1].rstrip("/")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Please set TELEGRAM_BOT_TOKEN env var.")
        sys.exit(1)

    path = os.getenv("WEBHOOK_PATH", "webhook")
    webhook_url = f"{base}/{path}"

    set_url = f"https://api.telegram.org/bot{token}/setWebhook"
    res = requests.post(set_url, json={"url": webhook_url})
    print(res.status_code, res.text)


if __name__ == "__main__":
    main()
