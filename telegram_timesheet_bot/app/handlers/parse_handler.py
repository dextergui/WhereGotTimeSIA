from .. import telegram_bot, ocr, service, sheets, config
from ..state import update, PENDING_UPLOADS


def start(chat_id):
    telegram_bot.send_message(chat_id, "Send an image to parse.")


def handle(chat_id, msg):

    file_id = None
    filename = None

    photos = msg.get("photo")
    if photos:
        file_id = photos[-1]["file_id"]

    doc = msg.get("document")
    if doc:
        file_id = doc.get("file_id")
        filename = doc.get("file_name")

    if not file_id:
        telegram_bot.send_message(chat_id, "Send an image.")
        return

    fi = telegram_bot.get_file_info(file_id)
    file_path = fi.get("file_path")

    if not file_path:
        telegram_bot.send_message(chat_id, "Could not access file.")
        return

    file_bytes = telegram_bot.download_file(file_path)

    if not file_bytes:
        telegram_bot.send_message(chat_id, "Download failed.")
        return

    try:
        extracted = ocr.extract_text_from_file(file_bytes, filename)
        parsed = service.parse_timesheet(extracted)
    except Exception:
        telegram_bot.send_message(chat_id, "Processing failed.")
        return

    reply_text = service.trips_to_message(parsed["entries"])
    sheet_rows = service.trips_to_sheet_rows(parsed["entries"])

    telegram_bot.send_message(chat_id, reply_text)

    if chat_id not in config.TRUSTED_CHAT_IDS:
        return

    PENDING_UPLOADS[chat_id] = sheet_rows

    keyboard = {
        "inline_keyboard": [[
            {"text": "Yes", "callback_data": "CONFIRM_YES"},
            {"text": "No", "callback_data": "CONFIRM_NO"}
        ]]
    }

    telegram_bot.send_message(
        chat_id,
        "Push to Google Sheets?",
        reply_markup=keyboard
    )

def callback(chat_id, data):

    if chat_id not in config.TRUSTED_CHAT_IDS:
        return

    if data == "CONFIRM_YES":

        pending = PENDING_UPLOADS.pop(chat_id, None)

        if not pending:
            telegram_bot.send_message(chat_id, "No pending data.")
            return

        try:
            sheet_id = config.SHEET_ID
            sheet_name = config.SHEET_NAME

            sheets.append_row(sheet_id, pending, sheet_name=sheet_name)

            telegram_bot.send_message(
                chat_id,
                "✅ Pushed to Google Sheets."
            )

        except Exception:
            telegram_bot.send_message(
                chat_id,
                "❌ Failed to push to Google Sheets."
            )

        return


    if data == "CONFIRM_NO":

        PENDING_UPLOADS.pop(chat_id, None)

        telegram_bot.send_message(
            chat_id,
            "Cancelled."
        )