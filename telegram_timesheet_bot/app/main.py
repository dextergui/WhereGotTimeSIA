"""FastAPI app that accepts Telegram webhook updates and processes uploads."""
from __future__ import annotations
import os
import time
import logging
from fastapi import FastAPI, Request, HTTPException

from . import config, telegram_bot, ocr, sheets

app = FastAPI()
logger = logging.getLogger("uvicorn.error")


@app.post("/{webhook_path}")
async def telegram_webhook(webhook_path: str, request: Request):
    if webhook_path != config.WEBHOOK_PATH:
        raise HTTPException(status_code=404, detail="Not found")

    update = await request.json()
    try:
        # handle message with photo or document
        msg = update.get("message") or {}
        chat = msg.get("chat", {})
        chat_id = chat.get("id")

        file_id = None
        filename = None

        # photos: choose highest resolution
        photos = msg.get("photo")
        if photos:
            file_id = photos[-1]["file_id"]

        doc = msg.get("document")
        if doc:
            file_id = doc.get("file_id")
            filename = doc.get("file_name")

        if not file_id:
            # nothing to do
            return {"ok": True}

        fi = telegram_bot.get_file_info(file_id)
        file_path = fi.get("file_path")
        if not file_path:
            telegram_bot.send_message(chat_id, "Sorry, couldn't access the file.")
            return {"ok": False}

        file_bytes = telegram_bot.download_file(file_path)

        if not file_bytes:
            telegram_bot.send_message(chat_id, "Failed to download file.")
            return {"ok": False}

        # OCR and parse
        text = ocr.extract_text_from_file(file_bytes, filename)
        parsed = ocr.parse_timesheet(text)

        # Build reply
        name = parsed.get("name") or "(unknown)"
        month = parsed.get("month") or "(unknown)"
        entries = parsed.get("entries") or []

        reply_lines = [f"Timesheet parsed for: {name}", f"Period: {month}", "Entries:"]
        reply_lines += entries[:20]
        reply_text = "\n".join(reply_lines)

        telegram_bot.send_message(chat_id, reply_text)

        # Append to Google Sheet if configured
        if os.getenv("SHEET_ID"):
            try:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                sheet_row = [ts, str(chat_id), name, month, " | ".join(entries[:50]), parsed.get("raw_text")[:2000]]
                sheets.append_row(os.getenv("SHEET_ID"), sheet_row, sheet_name=os.getenv("SHEET_NAME"))
            except Exception as e:
                logger.exception("Failed to append sheet: %s", e)
                telegram_bot.send_message(chat_id, "Parsed but failed to append to sheet.")

        return {"ok": True}
    except Exception as e:
        logger.exception("Processing failed: %s", e)
        return {"ok": False}


@app.get("/health")
def health():
    return {"status": "ok"}
