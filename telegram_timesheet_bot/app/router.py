from .state import get, set
from .handlers import parse_handler, availability_handler
from app import telegram_bot


def route_message(chat_id, text, msg):

    # commands override everything
    if text == "/parse":
        set(chat_id, {"mode": "parse", "step": "await_image"})
        return parse_handler.start(chat_id)

    if text == "/availability":
        set(chat_id, {
            "mode": "availability",
            "step": "await_name",
            "data": {"people": []}
        })
        return availability_handler.start(chat_id)

    state = get(chat_id)

    if not state:
        return parse_handler.start(chat_id)

    if state["mode"] == "parse":
        return parse_handler.handle(chat_id, msg)

    if state["mode"] == "availability":
        return availability_handler.handle(chat_id, text)
    
def route_callback(chat_id, data):

    state = get(chat_id)

    if not state:
        return

    if state["mode"] == "availability":
        return availability_handler.callback(chat_id, data)

    if state["mode"] == "parse":
        return parse_handler.callback(chat_id, data)