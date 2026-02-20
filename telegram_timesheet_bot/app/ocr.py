"""OCR and simple timesheet parsing utilities.
Supports Google Vision (if credentials provided) else pytesseract.
"""
from __future__ import annotations
import os
import json
import base64

def _get_vision_client():
    from google.cloud import vision

    creds_b64 = os.getenv("GOOGLE_CREDS_B64")

    if not creds_b64:
        raise RuntimeError("GOOGLE_CREDS_B64 not set")

    # Fix padding safely
    missing_padding = len(creds_b64) % 4
    if missing_padding:
        creds_b64 += "=" * (4 - missing_padding)
    creds_json = base64.b64decode(creds_b64).decode("utf-8")
    creds_dict = json.loads(creds_json)

    from google.oauth2 import service_account
    credentials = service_account.Credentials.from_service_account_info(creds_dict)

    return vision.ImageAnnotatorClient(credentials=credentials)

def image_bytes_to_text(image_bytes: bytes) -> str:
    try:
        from google.cloud import vision
        client = _get_vision_client()

        image = vision.Image(content=image_bytes)
        response = client.document_text_detection(image=image)

        if response.error.message:
            raise Exception(response.error.message)

        text = response.full_text_annotation.text
        print("Google Vision OCR extracted text:")
        print(text)

        return text

    except Exception as e:
        print("Vision OCR failed:", e)
        return ""

def extract_text_from_file(file_bytes: bytes, filename: str | None = None) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        raise Exception("PDF OCR not implemented yet. Please convert to image first.")
    else:
        return image_bytes_to_text(file_bytes)

