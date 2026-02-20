"""Small Telegram helper using Bot API via requests.
This keeps dependencies minimal and avoids long callback setups.
"""
from __future__ import annotations
import os
import requests
from typing import Optional

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{TOKEN}"


def send_message(chat_id: int, text: str, reply_markup=None) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    url = f"{API_URL}/sendMessage"
    res = requests.post(url, json=payload)
    return res.json()


def get_file_info(file_id: str) -> dict:
    url = f"{API_URL}/getFile"
    res = requests.get(url, params={"file_id": file_id})
    return res.json().get("result") or {}


def download_file(file_path: str) -> bytes | None:
    file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    r = requests.get(file_url)
    if r.status_code == 200:
        return r.content
    return None

def answer_callback_query(callback_query_id):
    requests.post(
        f"{API_URL}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id}
    )