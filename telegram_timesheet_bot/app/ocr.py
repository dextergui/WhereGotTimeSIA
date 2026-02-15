"""OCR and simple timesheet parsing utilities.
Supports Google Vision (if credentials provided) else pytesseract.
"""
from __future__ import annotations
import io
import os
import re
from typing import List, Dict

from PIL import Image

# Prefer EasyOCR (free, offline) if installed; otherwise fallback to pytesseract.
_easyocr_reader = None

def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is not None:
        return _easyocr_reader
    try:
        import easyocr

        # default to English; users can modify to include other languages
        _easyocr_reader = easyocr.Reader(["en"], gpu=False)
        return _easyocr_reader
    except Exception:
        return None


def image_bytes_to_text(image_bytes: bytes) -> str:
    # Try EasyOCR first
    reader = _get_easyocr_reader()
    if reader is not None:
        try:
            import numpy as np

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            arr = np.array(img)
            results = reader.readtext(arr, detail=0)
            return "\n".join([r for r in results if r])
        except Exception:
            pass

    # fallback to pytesseract
    try:
        import pytesseract

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


def pdf_bytes_to_images(pdf_bytes: bytes) -> List[bytes]:
    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(pdf_bytes)
        results = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            results.append(buf.getvalue())
        return results
    except Exception:
        return []


def extract_text_from_file(file_bytes: bytes, filename: str | None = None) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        imgs = pdf_bytes_to_images(file_bytes)
        texts = [image_bytes_to_text(b) for b in imgs]
        return "\n\n".join(texts)
    else:
        return image_bytes_to_text(file_bytes)


def parse_timesheet(text: str) -> Dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    duty_entries = []

    date_pattern = re.compile(r"^\d{2}\s?[A-Za-z]{3}\s?\d{2}")

    for line in lines:
        if not date_pattern.match(line):
            continue

        # split by 2+ spaces (column separation)
        cols = re.split(r"\s{2,}", line)

        try:
            start_date = cols[0]

            flight_number = None
            sector = None
            duty_type = None
            rpt = None
            std = None
            sta = None
            flight_time = None
            duty_time = None
            fdp = None

            # Extract known fields by scanning columns
            for c in cols:
                if "-" in c and len(c) == 7:  # e.g. CDG-SIN
                    sector = c
                elif c in ["FLY", "LO", "ATDO", "OFFD", "AALV", "SS60", "SS77"]:
                    duty_type = c
                elif re.match(r"^\d{4}$", c):  # 1805, 0520 etc
                    if not rpt:
                        rpt = c
                    elif not std:
                        std = c
                    elif not sta:
                        sta = c
                elif re.match(r"^\d{1,2}:\d{2}$", c):  # 13:45
                    if not flight_time:
                        flight_time = c
                    elif not duty_time:
                        duty_time = c
                    elif not fdp:
                        fdp = c

            origin = None
            destination = None
            if sector and "-" in sector:
                origin, destination = sector.split("-")

            # Determine Layover vs Turnaround
            duty_classification = None
            if duty_type == "FLY":
                duty_classification = "Turnaround"
            elif duty_type == "LO":
                duty_classification = "Layover"
            else:
                duty_classification = duty_type

            duty_entries.append({
                "start_date": start_date,
                "origin": origin,
                "destination": destination,
                "sector": sector,
                "duty_type": duty_type,
                "classification": duty_classification,
                "rpt": rpt,
                "std": std,
                "sta": sta,
                "flight_time": flight_time,
                "duty_time": duty_time,
                "fdp": fdp,
            })

        except Exception:
            continue

    return {
        "entries": duty_entries,
        "raw_text": text
    }
