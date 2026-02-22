"""OCR and simple timesheet parsing utilities.
Supports Google Vision (if credentials provided) else pytesseract.
"""
from __future__ import annotations
import os
import json
import base64
import math
from typing import List, Dict

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

def _fill_missing_vertices(vertices):
    fixed = []
    for v in vertices:
        x = v.x if v.x is not None else 0
        y = v.y if v.y is not None else 0
        fixed.append({"x": x, "y": y})
    return fixed


def group_words_by_line(text_annotations, y_threshold_ratio=0.6):
    words = []

    # Skip index 0 (full text blob)
    for item in text_annotations[1:]:
        if not item.bounding_poly or not item.bounding_poly.vertices:
            continue

        vertices = _fill_missing_vertices(item.bounding_poly.vertices)

        words.append({
            "text": item.description,
            "vertices": vertices,
            "avg_y": sum(v["y"] for v in vertices) / 4,
            "avg_x": sum(v["x"] for v in vertices) / 4,
            "height": abs(vertices[0]["y"] - vertices[3]["y"]),
        })

    # Sort top → bottom
    words.sort(key=lambda w: w["avg_y"])

    lines = []
    current_line = []
    current_y = None
    current_height = None

    for word in words:
        if not current_line:
            current_line = [word]
            current_y = word["avg_y"]
            current_height = word["height"]
            continue

        y_diff = abs(word["avg_y"] - current_y)
        threshold = current_height * y_threshold_ratio

        if y_diff <= threshold:
            current_line.append(word)
        else:
            lines.append(current_line)
            current_line = [word]
            current_y = word["avg_y"]
            current_height = word["height"]

    if current_line:
        lines.append(current_line)

    # Sort left → right
    final_lines = []
    for line in lines:
        line.sort(key=lambda w: w["avg_x"])
        final_lines.append(" ".join(w["text"] for w in line))

    return final_lines

def image_bytes_to_text(image_bytes: bytes) -> str:
    try:
        from google.cloud import vision
        client = _get_vision_client()

        image = vision.Image(content=image_bytes)
        response = client.document_text_detection(image=image)

        if response.error.message:
            raise Exception(response.error.message)

        annotations = response.text_annotations

        if not annotations:
            return ""

        lines = group_words_by_line(annotations)
        return "\n".join(lines)

    except Exception as e:
        print("Vision OCR failed:", e)
        return ""

def extract_text_from_file(file_bytes: bytes, filename: str | None = None) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        raise Exception("PDF OCR not implemented yet. Please convert to image first.")
    else:
        return image_bytes_to_text(file_bytes)

