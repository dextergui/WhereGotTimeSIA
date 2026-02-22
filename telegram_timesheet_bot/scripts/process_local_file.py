"""Process a local image or PDF like the webhook would.

Prints the reply message and the sheet row that would be appended.
Optionally append to Google Sheets if `--append` is given and `SHEET_ID` is set.

Usage:
  python scripts/process_local_file.py path/to/file.jpg [--chat 12345] [--append]
"""
import sys
import os
import base64
import argparse
from pathlib import Path

# Ensure project root is on sys.path so `from app import ...` works when
# running this script as `python scripts/process_local_file.py ...`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from app import ocr, sheets, service

def main():
    p = argparse.ArgumentParser()
    p.add_argument("file", help="Path to image or PDF")
    p.add_argument("--chat", type=int, help="Chat id to include in row/reply")
    p.add_argument("--append", action="store_true", help="Actually append to Google Sheet (requires SHEET_ID + creds)")
    p.add_argument("--mock", help="Path to raw OCR text file (skip Vision API)")
    args = p.parse_args()

    path = args.file
    if not os.path.exists(path):
        print("File not found:", path)
        sys.exit(1)

    if args.mock:
        print("Using mock OCR text from:", args.mock)
        with open(args.mock, "r", encoding="utf-8") as f:
            extracted_text = f.read()
    else:
        with open(path, "rb") as f:
            data = f.read()
        extracted_text = ocr.extract_text_from_file(data, filename=path)
        
    # print("=== RAW OCR TEXT ===")
    # print(extracted_text)
    # print("====================")

    parsed = service.parse_timesheet(extracted_text)
    trips = service.group_trips(parsed["entries"])

    reply = service.trips_to_message(trips)
    row = service.trips_to_sheet_rows(trips)

    print("--- Reply message ---")
    print(reply)
    print()
    print("--- Sheet row (ready to append) ---")
    for i, v in enumerate(row, 1):
        print(f"{i}:", (v if len(str(v)) < 200 else str(v)[:200] + '...'))

    if args.append:
        sheet_id = os.getenv("SHEET_ID")
        if not sheet_id:
            print("SHEET_ID not set; cannot append. Set SHEET_ID env var to enable append.")
            sys.exit(1)
        sheet_name = os.getenv("SHEET_NAME")
        print("Appending to sheet... (sheet: %s)" % (sheet_name or 'sheet1'))
        sheets.append_row(sheet_id, row, sheet_name=sheet_name)
        print("Appended.")


if __name__ == "__main__":
    main()
