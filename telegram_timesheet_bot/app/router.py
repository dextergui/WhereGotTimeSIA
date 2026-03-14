from .state import get, set, clear, PENDING_UPLOADS
from .handlers import parse_handler, availability_handler
from app import telegram_bot


def route_message(chat_id, text, msg):

    # commands override everything
    if text == "/health":
        telegram_bot.send_message(chat_id, "🟢 System is alive.")
        return {"ok": True}

    if text == "/extract":
        set(chat_id, {"mode": "parse", "step": "await_image"})
        return parse_handler.start(chat_id)

    if text == "/availability":
        set(chat_id, {
            "mode": "availability",
            "step": "await_name",
            "data": {"people": []}
        })
        return availability_handler.start(chat_id)

    if text == "/cancel":
        clear(chat_id)
        PENDING_UPLOADS.pop(chat_id, None)

        telegram_bot.send_message(
            chat_id,
            "❌ Current operation cancelled.\n\n" + INSTRUCTION_TEXT
        )
        return
    
    state = get(chat_id)

    if not state:
        # Reply with instructions
        INSTRUCTION_TEXT = """
        🤖 Bot Usage

        /health → Check the status of the bot  
        /extract → Send image to extract trips  
        /availability → Find common availability between crews

        /cancel → Cancel current mode
        You can use the commands anytime.
        """
        telegram_bot.send_message(chat_id, INSTRUCTION_TEXT)
        return {"ok": True}

    if state["mode"] == "parse":
        return parse_handler.handle(chat_id, msg)

    if state["mode"] == "availability":
        return availability_handler.handle(chat_id, text)
    
def route_callback(chat_id, data):

    state = get(chat_id)

    if not state:
        return

    if data in ("CONFIRM_YES", "CONFIRM_NO"):
        return parse_handler.callback(chat_id, data)

    if data in ("ADD_MORE", "START_SEARCH"):
        return availability_handler.callback(chat_id, data)