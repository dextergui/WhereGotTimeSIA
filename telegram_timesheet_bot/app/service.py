"""Timesheet processing service.
Parsing and processing logic for extracting structured data from timesheet images, and appending to Google Sheets.
"""

import datetime
import re
from typing import List, Dict

HOME_DUTY_REGEX = re.compile(r"^(ATDO|AALV|OFFD|SS\d+)$")


def _parse_date_str(date_str: str) -> datetime.date:
    """Convert '01Mar26' → datetime.date(2026,3,1)"""
    return datetime.datetime.strptime(date_str, "%d%b%y").date()


def parse_timesheet(text: str) -> Dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    date_pattern = re.compile(r"\d{2}[A-Za-z]{3}\d{2}")

    duty_entries = []
    current_block = []
    current_date = None

    for line in lines:
        date_match = date_pattern.search(line)

        if date_match:
            # Save previous block if exists
            if current_block:
                duty_entries.extend(
                    _parse_block(current_date, current_block)
                )
                current_block = []

            current_date = date_match.group()
            current_block.append(line)

        elif current_block:
            current_block.append(line)

    # Add last block
    if current_block:
        duty_entries.extend(
            _parse_block(current_date, current_block)
        )

    merged_entries = merge_split_flights(duty_entries)

    return {
        "entries": merged_entries,
        "raw_text": text
    }


def merge_split_flights(entries: list[dict]) -> list[dict]:
    merged = []

    for e in entries:
        if not merged:
            merged.append(e)
            continue

        prev = merged[-1]

        # Only merge if:
        # same flight + same sector
        # AND previous missing STA
        if (
            e.get("flight_number")
            and prev.get("flight_number") == e.get("flight_number")
            and prev.get("sector") == e.get("sector")
            and not prev.get("sta")
        ):
            if e.get("sta"):
                prev["sta"] = e["sta"]
            if not prev.get("rpt") and e.get("rpt"):
                prev["rpt"] = e["rpt"]
            continue

        merged.append(e)

    return merged




def _parse_block(date, block_lines):
    entries = []

    text = "\n".join(block_lines)

    # Split by each SQ occurrence
    flight_sections = re.split(r"(SQ\s?\d+)", text)

    # re.split keeps delimiters → pair them
    for i in range(1, len(flight_sections), 2):
        flight_token = flight_sections[i]
        section_text = flight_token + flight_sections[i + 1]

        sector_match = re.search(r"[A-Z]{3}-[A-Z]{3}", section_text)
        if not sector_match:
            continue

        sector = sector_match.group()
        origin, destination = sector.split("-")

        flight_number = flight_token.replace(" ", "")

        times = re.findall(r"\b\d{4}\b", section_text)

        rpt = times[0] if len(times) >= 1 else None
        std = times[1] if len(times) >= 2 else None
        sta = times[2] if len(times) >= 3 else (
              times[-1] if len(times) >= 1 else None
        )

        entries.append({
            "start_date": date,
            "flight_number": flight_number,
            "sector": sector,
            "origin": origin,
            "destination": destination,
            "duty_type": "FLY",
            "rpt": rpt,
            "std": std,
            "sta": sta,
            "raw_block": section_text
        })

    # Handle SS standby separately
    if "SS" in text:
        ss_match = re.search(r"(SS\d+)", text)
        if ss_match:
            times = re.findall(r"\b\d{4}\b", text)
            entries.append({
                "start_date": date,
                "flight_number": None,
                "sector": None,
                "origin": None,
                "destination": None,
                "duty_type": ss_match.group(),
                "rpt": times[0] if len(times) >= 1 else None,
                "std": None,
                "sta": times[2] if len(times) >= 3 else None,
                "raw_block": text
            })

    return entries



def group_trips(entries: list[dict]) -> list[list[dict]]:
    trips = []
    current = []

    for e in entries:
        duty = e.get("duty_type")

        # Standby → isolated
        if duty and duty.startswith("SS"):
            if current:
                trips.append(current)
                current = []
            trips.append([e])
            continue

        if duty != "FLY":
            continue

        origin = e.get("origin")
        destination = e.get("destination")

        # Broken arrival (CDG-SIN at start)
        if origin != "SIN" and destination == "SIN" and not current:
            trips.append([e])
            continue

        # Outbound from SIN starts new trip
        if origin == "SIN":
            if current:
                trips.append(current)
            current = [e]
            continue

        # Inbound to SIN ends trip
        if destination == "SIN":
            if current:
                current.append(e)
                trips.append(current)
                current = []
            else:
                trips.append([e])
            continue

        # Any other FLY in between
        if current:
            current.append(e)

    if current:
        trips.append(current)

    return trips




def trips_to_message(trips: list[list[dict]]) -> str:
    lines = ["Flights:"]

    for trip in trips:
        e0 = trip[0]
        start = e0["start_date"]
        end = trip[-1]["start_date"]

        # Standby
        if e0.get("duty_type", "").startswith("SS"):
            lines.append(
                f"{start} - {end} | {e0['duty_type']} | "
                f"{e0.get('rpt','-')} | {e0.get('sta','-')}"
            )
            continue

        fly = [e for e in trip if e.get("duty_type") == "FLY"]
        if not fly:
            continue

        first = fly[0]
        last = fly[-1]

        # Broken arrival (arrival only)
        if first["origin"] != "SIN" and first["destination"] == "SIN":
            lines.append(
                f"{start} - {end} | {first['sector']} | - | "
                f"{first.get('sta','-')} ({first.get('flight_number','')})"
            )
            continue

        # Determine outbound and inbound
        outbound = None
        inbound = None

        for e in fly:
            if e["origin"] == "SIN":
                outbound = e
            if e["destination"] == "SIN":
                inbound = e

        if outbound and inbound:
            lines.append(
                f"{start} - {end} | {outbound['destination']} | "
                f"{outbound.get('rpt','-')} ({outbound.get('flight_number','')}) | "
                f"{inbound.get('sta','-')} ({inbound.get('flight_number','')})"
            )

    return "\n".join(lines)


def trips_to_sheet_rows(trips: list[list[dict]]) -> list[list]:
    rows = []

    for trip in trips:
        fly = [e for e in trip if e.get("duty_type") == "FLY"]
        if not fly:
            continue

        start_date = _parse_date_str(trip[0]["start_date"])
        end_date = _parse_date_str(trip[-1]["start_date"])

        all_dates = [
            start_date + datetime.timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]

        fly_by_date = {
            _parse_date_str(e["start_date"]): e
            for e in fly
        }

        # Determine if turnaround (2 flights same day)
        turnaround = (
            len(fly) == 2 and
            fly[0]["start_date"] == fly[1]["start_date"]
        )

        station = None
        if fly:
            first = fly[0]
            if first["origin"] == "SIN":
                station = first["destination"]
            else:
                station = first["origin"]

        for d in all_dates:
            e = fly_by_date.get(d)
            date_str = d.strftime("%m/%d/%Y")

            if e:
                dep = e.get("origin") or ""
                arr = e.get("destination") or ""

                ftype = "Turnaround" if turnaround else "Layover"

                rpt = _format_time(e.get("rpt"))
                std = _format_time(e.get("std"))
                sta = _format_time(e.get("sta"))

                row = [
                    date_str,        # A Date
                    dep,             # B From
                    arr,             # C To
                    ftype,           # D Type
                    rpt if dep == "SIN" else "",  # E
                    sta if dep == "SIN" else "",  # F
                    rpt if dep != "SIN" else "",  # G
                    sta if dep != "SIN" else "",  # H
                    "", "", "", "", ""            # I–M (durations not handled here)
                ]

            else:
                # Intermediate layover day (no flight)
                row = [
                    date_str,   # A
                    "",         # B
                    station,    # C
                    "Layover",  # D
                    "", "", "", "",
                    "", "", "", "", ""
                ]

            rows.append(row)

    return rows



def _format_time(t):
    if not t:
        return ""
    return f"{t[:2]}:{t[2:]}"
