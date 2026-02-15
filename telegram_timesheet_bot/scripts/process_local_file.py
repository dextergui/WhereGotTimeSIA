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

from app import ocr, sheets


def build_reply(parsed, chat_id=None):
    name = parsed.get("name") or "(unknown)"
    month = parsed.get("month") or "(unknown)"
    entries = parsed.get("entries") or []
    lines = [f"Timesheet parsed for: {name}", f"Period: {month}", "Entries:"]
    lines += entries[:20]
    return "\n".join(lines)


def build_sheet_row(parsed, chat_id=None):
    import time
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    name = parsed.get("name") or ""
    month = parsed.get("month") or ""
    entries = parsed.get("entries") or []
    raw = parsed.get("raw_text") or ""
    row = [ts, str(chat_id or "local"), name, month, " | ".join(entries[:50]), raw[:2000]]
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file", help="Path to image or PDF")
    p.add_argument("--chat", type=int, help="Chat id to include in row/reply")
    p.add_argument("--append", action="store_true", help="Actually append to Google Sheet (requires SHEET_ID + creds)")
    args = p.parse_args()

    path = args.file
    if not os.path.exists(path):
        print("File not found:", path)
        sys.exit(1)

    with open(path, "rb") as f:
        data = f.read()

    parsed = ocr.extract_text_from_file(data, filename=path)
    # If extract_text_from_file returns text, we need to parse
    parsed = ocr.parse_timesheet(parsed)

    reply = build_reply(parsed, chat_id=args.chat)
    row = build_sheet_row(parsed, chat_id=args.chat)

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
