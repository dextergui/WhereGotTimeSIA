"""FastAPI app that accepts Telegram webhook updates and processes uploads."""
from __future__ import annotations
import os
import time
import logging
from fastapi import FastAPI, Request, HTTPException

from . import config, telegram_bot, ocr, sheets, service

app = FastAPI()
logger = logging.getLogger("uvicorn.error")
PENDING_UPLOADS: dict[int, dict] = {}


@app.post("/{webhook_path}")
async def telegram_webhook(webhook_path: str, request: Request):
    if webhook_path != config.WEBHOOK_PATH:
        raise HTTPException(status_code=404, detail="Not found")

    update = await request.json()

    # ======================
    # CALLBACK HANDLER
    # ======================
    callback = update.get("callback_query")
    if callback:
        chat_id = callback["message"]["chat"]["id"]
        data = callback.get("data")
        callback_id = callback.get("id")

        if chat_id not in config.TRUSTED_CHAT_IDS:
            return {"ok": True}

        telegram_bot.answer_callback_query(callback_id)

        if data == "CONFIRM_YES":
            pending = PENDING_UPLOADS.pop(chat_id, None)
            logger.info("Pushing SheetRows: \n", pending)
            if not pending:
                telegram_bot.send_message(chat_id, "No pending data.")
                return {"ok": True}

            try:
                sheet_id = os.getenv("SHEET_ID")
                if not sheet_id:
                    print("SHEET_ID not set; cannot append. Set SHEET_ID env var to enable append.")
                    raise Exception("SHEET_ID not set; cannot append. Set SHEET_ID env var to enable append.")
                sheet_name = os.getenv("SHEET_NAME")
                sheets.append_row(sheet_id, pending, sheet_name=sheet_name)
                telegram_bot.send_message(
                    chat_id,
                    "✅ Pushed to Google Sheets.\n\n" + config.INSTRUCTION_TEXT,
                )
            except Exception as e:
                logger.exception("Sheet error: %s", e)
                telegram_bot.send_message(chat_id, "❌ Failed to push.")

            return {"ok": True}

        if data == "CONFIRM_NO":
            PENDING_UPLOADS.pop(chat_id, None)
            telegram_bot.send_message(
                chat_id,
                "Cancelled.\n\n" + config.INSTRUCTION_TEXT,
            )
            return {"ok": True}

        return {"ok": True}

    # ======================
    # MESSAGE HANDLER
    # ======================
    msg = update.get("message")
    if not msg:
        return {"ok": True}

    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = msg.get("text")

    if chat_id not in config.TRUSTED_CHAT_IDS:
        telegram_bot.send_message(chat_id, "Access denied.")
        return {"ok": True}

    # ---- /start ----
    if text == "/start":
        telegram_bot.send_message(chat_id, config.INSTRUCTION_TEXT)
        return {"ok": True}

    # ---- /health ----
    if text == "/health":
        telegram_bot.send_message(chat_id, "🟢 System is alive.")
        return {"ok": True}

    # ---- Extract file ----
    file_id = None
    filename = None

    photos = msg.get("photo")
    if photos:
        file_id = photos[-1]["file_id"]

    doc = msg.get("document")
    if doc:
        file_id = doc.get("file_id")
        filename = doc.get("file_name")

    # If not file → show instructions
    if not file_id:
        telegram_bot.send_message(chat_id, config.INSTRUCTION_TEXT)
        return {"ok": True}

    # ======================
    # FILE PROCESSING
    # ======================
    fi = telegram_bot.get_file_info(file_id)
    file_path = fi.get("file_path")

    if not file_path:
        telegram_bot.send_message(chat_id, "Couldn't access file.")
        return {"ok": True}

    file_bytes = telegram_bot.download_file(file_path)

    if not file_bytes:
        telegram_bot.send_message(chat_id, "Download failed.")
        return {"ok": True}

    # OCR + Parse
    try:
        extracted_text = ocr.extract_text_from_file(file_bytes, filename)
        parsed = service.parse_timesheet(extracted_text)
        reply_text = service.trips_to_message(parsed["entries"])
        sheet_rows = service.trips_to_sheet_rows(parsed["entries"])
    except Exception as e:
        logger.exception("Processing failed: %s", e)
        telegram_bot.send_message(chat_id, "Processing failed.")
        return {"ok": True}

    # Store pending confirmation
    PENDING_UPLOADS[chat_id] = {
        "sheet_rows": sheet_rows,
    }

    # Inline confirmation buttons
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Yes", "callback_data": "CONFIRM_YES"},
                {"text": "No", "callback_data": "CONFIRM_NO"},
            ]
        ]
    }

    telegram_bot.send_message(
        chat_id,
        reply_text
    )
    telegram_bot.send_message(
        chat_id,
        "Push data to Google Sheets?",
        reply_markup=keyboard,
    )

    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}