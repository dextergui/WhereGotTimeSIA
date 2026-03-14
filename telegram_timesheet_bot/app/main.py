import logging

from fastapi import FastAPI, Request
from . import router
from app import telegram_bot, config

app = FastAPI()
logger = logging.getLogger("uvicorn.error")

def isAuthorized(chat_id: any):
    return (
        chat_id in config.ALLOWED_TO_USE_BOT_CHAT_IDS
        or chat_id in config.TRUSTED_CHAT_IDS
    )

@app.post("/{webhook_path}")
async def telegram_webhook(webhook_path: str, request: Request):

    update = await request.json()

    callback = update.get("callback_query")

    if callback:

        chat_id = callback["message"]["chat"]["id"]
        if not isAuthorized(chat_id):
            telegram_bot.answer_callback_query(
                callback["id"],
                text="❌ You are not authorized to use this bot.",
                show_alert=True
            )
            return {"ok": True}
        
        data = callback["data"]
        callback_id = callback["id"]

        telegram_bot.answer_callback_query(callback_id)
        router.route_callback(chat_id, data)

        return {"ok": True}


    msg = update.get("message")

    if not msg:
        return {"ok": True}

    chat_id = msg["chat"]["id"]
    if not isAuthorized(chat_id):
        telegram_bot.send_message(
            chat_id,
            "❌ You are not authorized to use this bot."
        )
        return {"ok": True}
    text = msg.get("text")

    router.route_message(chat_id, text, msg)

    return {"ok": True}

@app.get("/health")
def health():
    return {"status": "ok"}