# Telegram Timesheet OCR Bot

This is a minimal Python FastAPI service intended to be hosted on Render and used as a Telegram webhook. It accepts images or PDFs sent to your Telegram bot, runs OCR (EasyOCR preferred, pytesseract fallback), extracts basic timesheet fields, replies in Telegram, and appends a summary row to a Google Sheet.

Environment variables (required):

- `TELEGRAM_BOT_TOKEN` — your bot token
- `SHEET_ID` — Google Sheet ID to append rows to (optional)
- `SHEET_NAME` — (optional) worksheet title within the Google Sheet to append rows to. If omitted the first sheet (`sheet1`) will be used.
- `GOOGLE_CREDS_B64` — base64-encoded Google service account JSON (recommended) or raw JSON string (optional but required for Sheets integration)
- `WEBHOOK_PATH` — path segment the webhook will listen on (default `webhook`)

Notes:

This project prefers `EasyOCR` (no cloud account required). If EasyOCR is not installed or available, it falls back to `pytesseract`, which requires the `tesseract` binary to be installed in the environment.

- For PDFs, `pdf2image` is used and requires `poppler` installed in the host image.

Deploy to Render (summary):

1. Create a Python web service on Render.
2. Set `Start Command` to: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Add environment variables listed above in Render dashboard.
4. Point your Telegram bot webhook to `https://<your-render-service>.onrender.com/<WEBHOOK_PATH>`

Example run locally:

Install deps:

```
pip install -r requirements.txt
```

Run:

```
uvicorn app.main:app --reload
```

## Webhook setup and testing

Set your webhook URL (replace with your render service URL):

```
python scripts/set_webhook.py https://<your-render-service>.onrender.com
```

Or set it manually with curl:

```
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" -H "Content-Type: application/json" -d '{"url":"https://<your-render-service>.onrender.com/<WEBHOOK_PATH>"}'
```

To test locally (run uvicorn first):

```
python scripts/local_test_update.py
```

If you use Google APIs, provide a base64 service account JSON in `GOOGLE_CREDS_B64` or set `GOOGLE_APPLICATION_CREDENTIALS` to a file path.

To append to a specific worksheet inside the Sheet, set `SHEET_NAME` to the worksheet title. If the worksheet does not exist it will be created automatically.
