"""
Test calendar event creation locally.

Usage:
  python scripts/test_calendar.py path/to/file.jpg
  python scripts/test_calendar.py path/to/file.jpg --mock text.txt
  python scripts/test_calendar.py path/to/file.jpg --push

Options:
  --mock   Use OCR text file instead of Vision API
  --push   Actually push events to Google Calendar
"""

import sys
import os
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from app import ocr, service, calendar


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file", help="Path to image/PDF")
    p.add_argument("--mock", help="Path to OCR text file")
    p.add_argument("--push", action="store_true", help="Push to Google Calendar")
    args = p.parse_args()

    if not os.path.exists(args.file):
        print("File not found:", args.file)
        sys.exit(1)

    # --- OCR ---
    if args.mock:
        print("Using mock OCR:", args.mock)
        with open(args.mock, "r", encoding="utf-8") as f:
            extracted_text = f.read()
    else:
        with open(args.file, "rb") as f:
            extracted_text = ocr.extract_text_from_file(f.read(), args.file)

    # --- Parse ---
    parsed = service.parse_timesheet(extracted_text)
    entries = parsed["entries"]
    trips = service.group_trips(entries)

    print("\n=== TRIPS DETECTED ===")

    preview_events = []

    for i, trip in enumerate(trips, 1):

        fly = [e for e in trip if e.duty_type == "FLY"]
        if not fly:
            continue

        outbound = next((f for f in fly if f.origin == "SIN"), None)
        inbound = next((f for f in reversed(fly) if f.destination == "SIN"), None)

        if not outbound or not inbound:
            print(f"[{i}] Skipped (broken trip)")
            continue

        start = calendar._build_dt(outbound, use_rpt=True)
        end = calendar._build_dt(inbound, is_end=True)

        if not start or not end:
            print(f"[{i}] Skipped (missing time)")
            continue

        summary = f"{outbound.destination} Trip"

        event = {
            "summary": summary,
            "location": outbound.destination,
            "description": f"{outbound.flight_number} {outbound.sector} → {inbound.flight_number} {inbound.sector}",
            "start": start,
            "end": end,
        }

        preview_events.append(event)

        print(f"\n[{i}] {summary}")
        print(f"  Start: {start}")
        print(f"  End  : {end}")
        print(f"  Desc : {event['description']}")

    print("\n=== SUMMARY ===")
    print(f"{len(preview_events)} events ready")

    # --- Push ---
    if args.push:
        print("\nPushing to Google Calendar...")
        calendar.push_events(trips)
        print("Done.")
    else:
        print("\nDry run only. Use --push to insert into calendar.")


if __name__ == "__main__":
    main()