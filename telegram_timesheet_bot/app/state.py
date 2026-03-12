CHAT_STATE: dict[int, dict] = {}
PENDING_UPLOADS: dict[int, list[list]] = {}

def get(chat_id: int):
    return CHAT_STATE.get(chat_id)

def set(chat_id: int, state: dict):
    CHAT_STATE[chat_id] = state

def update(chat_id: int, **kwargs):
    CHAT_STATE.setdefault(chat_id, {}).update(kwargs)

def clear(chat_id: int):
    CHAT_STATE.pop(chat_id, None)