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

def _split_duration(hhmm: str | None):
    if not hhmm or ":" not in hhmm:
        return "", ""
    h, m = hhmm.split(":")
    return h, m

def _is_overnight(entry: dict) -> bool:
    """
    Detect if a flight is overnight (arrives next calendar day).
    Rule: STA < RPT (both as HHMM integers) — the clock wrapped past midnight.
    Requires both rpt and sta to be set.
    """
    rpt = entry.get("rpt")
    sta = entry.get("sta")
    if rpt and sta:
        return int(sta) < int(rpt)
    return False


def parse_timesheet(text: str) -> Dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    date_pattern = re.compile(r"\d{2}\s?[A-Za-z]{3}\d{2}")

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

            current_date = date_match.group().replace(" ", "")
            current_block.append(line)

        elif current_block:
            current_block.append(line)

    # Add last block
    if current_block:
        duty_entries.extend(
            _parse_block(current_date, current_block)
        )
    
    for e in duty_entries:
        print(f"{e.get('start_date')} | {e.get('flight_number')} | {e.get('sector')} | {e.get('origin')}|{e.get('destination')} | RPT: {e.get('rpt')} | STD: {e.get('std')} | STA: {e.get('sta')} | Flight: {e.get('flight_time')} | Duty: {e.get('duty_time')}  | FDP: {e.get('fdp')}")

    merged_entries = merge_split_flights(duty_entries)
    merged_entries = fix_misplaced_overnight_departures(merged_entries)

    return {
        "entries": merged_entries,
        "raw_text": text
    }

def fix_misplaced_overnight_departures(entries: list[dict]) -> list[dict]:
    for i in range(1, len(entries)):
        curr = entries[i]
        prev = entries[i - 1]

        if (
            curr.get("flight_number")
            and prev.get("flight_number") == curr.get("flight_number")
            and prev.get("sector") == curr.get("sector")
            and not prev.get("std")
            and curr.get("std")
            and curr.get("sta")
        ):
            # Move STD + flight_time to previous day
            prev["std"] = curr["std"]
            prev["flight_time"] = curr.get("flight_time")

            # Current day keeps only STA
            curr["std"] = None
            curr["flight_time"] = None

    return entries

def merge_split_flights(entries: list[dict]) -> list[dict]:
    """
    Merge continuation blocks for the same flight.
    A continuation block is a block on the next date that carries only the STA
    for a flight that started the previous day (overnight flight).

    Match criteria: same flight_number + same sector, and previous entry missing STA.
    """
    merged = []

    for e in entries:
        if not merged:
            merged.append(e)
            continue

        prev = merged[-1]

        # Continuation if same flight and sector and previous missing STA
        if (
            e.get("flight_number")
            and prev.get("flight_number") == e.get("flight_number")
            and prev.get("sector") == e.get("sector")
        ):

            # Case 1: continuation day has only STA
            if e.get("sta") and not e.get("std") and not prev.get("sta"):
                prev["sta"] = e["sta"]
                prev["arrival_date"] = e["start_date"]
                continue

            # Case 2: continuation day has STD + STA (overnight outbound)
            if e.get("std") and e.get("sta"):
                # keep as separate entry
                merged.append(e)
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
            # Try to inherit sector from next block
            next_sector = None
            if i + 2 < len(flight_sections):
                next_text = flight_sections[i + 2]
                next_sector_match = re.search(r"[A-Z]{3}-[A-Z]{3}", next_text)
                if next_sector_match:
                    next_sector = next_sector_match.group()

            if not next_sector:
                continue

            sector = next_sector
        else:
            sector = sector_match.group()

        sector = sector_match.group()
        origin, destination = sector.split("-")

        flight_number = flight_token.replace(" ", "")

        times = re.findall(r"\b\d{4}\b", section_text)
        durations = re.findall(r"\b\d{2}:\d{2}\b", section_text)

        rpt = None
        std = None
        sta = None
        flightTime = None
        dutyTime = None
        fdp = None

        if len(times) >= 3:
            # Normal case: RPT STD STA
            rpt = times[0]
            std = times[1]
            sta = times[2]
        elif len(times) == 2 and len(durations) == 1:
            # Overnight flight with missing RPT (e.g. dep on 31st, arrives next month with no RPT shown)
            # In this case we have STD + STA but no RPT, and the single duration is the flight time.
            std = times[0]
            sta = times[1]
        elif len(times) == 2 and len(durations) > 1:
            # RPT + STD only (STA on next day)
            rpt = times[0]
            std = times[1]
        elif len(times) == 1:
            if "SIN-" in sector:
                # outbound start
                rpt = times[0]
            else:
                sta = times[0]

        if len(durations) >= 3:
            # normal case: Flight Time, Duty Time, FDP
            flightTime = durations[0]
            dutyTime = durations[1]
            fdp = durations[2]
        elif len(durations) == 2:
            # only Duty Time and FDP shown (e.g. for standby duty)
            dutyTime = durations[0]
            fdp = durations[1]
        elif len(durations) == 1:
            if "SIN-" not in sector and len(times) == 2:
                # continuation arrival block → duration is flight time
                flightTime = durations[0]
            else:
                fdp = durations[0]

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
            "flight_time": flightTime,
            "duty_time": dutyTime,
            "fdp": fdp,
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

        # Standby → isolated block
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

        # Broken arrival (e.g. CDG-SIN at start of month — no outbound in this period)
        if origin != "SIN" and destination == "SIN" and not current:
            trips.append([e])
            continue

        # Start new trip ONLY if not already in one
        if origin == "SIN" and not current:
            current = [e]
            continue

        # If already in trip, just append
        if current:
            current.append(e)

            # End trip when inbound flight lands at SIN and has STA
            if destination == "SIN" and e.get("sta"):
                trips.append(current)
                current = []

            continue

    if current:
        trips.append(current)

    return trips


def _trip_end_date(trip: list[dict]) -> str:
    """
    Return the effective end date for a trip.
    For overnight inbound legs (STA < RPT), the trip ends the following day.
    """
    fly = [e for e in trip if e.get("duty_type") == "FLY"]
    if not fly:
        return trip[-1]["start_date"]

    last = fly[-1]
    arrival_date = last.get("arrival_date", last["start_date"])
    base = _parse_date_str(arrival_date)

    # If the last flight is an inbound overnight, end date is +1
    if last.get("destination") == "SIN" and _is_overnight(last):
        base += datetime.timedelta(days=1)

    return base.strftime("%d%b%y")


def trips_to_message(trips: list[list[dict]]) -> str:
    lines = ["Flights:"]

    for trip in trips:
        e0 = trip[0]
        start = e0["start_date"]

        # Standby
        if e0.get("duty_type", "").startswith("SS"):
            end = trip[-1]["start_date"]
            lines.append(
                f"{start} - {end} | {e0['duty_type']} | "
                f"{e0.get('rpt','-')} | {e0.get('sta','-')}"
            )
            continue

        fly = [e for e in trip if e.get("duty_type") == "FLY"]
        if not fly:
            continue

        first = fly[0]

        # Compute effective end date (accounts for overnight inbound)
        end = _trip_end_date(trip)

        # Broken arrival (arrival only — inbound only trip, no outbound in period)
        if first["origin"] != "SIN" and first["destination"] == "SIN":
            lines.append(
                f"{start} - {end} | {first['sector']} | - | "
                f"{first.get('sta','-')} ({first.get('flight_number','')})"
            )
            continue

        # Determine outbound and inbound legs
        outbound = next((e for e in fly if e["origin"] == "SIN"), None)
        inbound = next((e for e in reversed(fly) if e["destination"] == "SIN"), None)

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

        start_date = _parse_date_str(fly[0]["start_date"])
        last = fly[-1]
        end_date = _parse_date_str(last["start_date"])

        # inbound overnight extends one day
        if last.get("destination") == "SIN" and _is_overnight(last):
            end_date += datetime.timedelta(days=1)

        turnaround = (
            len(fly) == 2 and
            fly[0]["start_date"] == fly[1]["start_date"]
        )

        station = fly[0]["destination"] if fly[0]["origin"] == "SIN" else fly[0]["origin"]

        # map date → flights
        fly_by_date: dict[datetime.date, list[dict]] = {}
        for e in fly:
            d = _parse_date_str(e["start_date"])
            fly_by_date.setdefault(d, []).append(e)

        all_dates = [
            start_date + datetime.timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]

        for d in all_dates:
            date_str = d.strftime("%m/%d/%Y")
            entries_today = fly_by_date.get(d, [])

            if turnaround and entries_today:
                for e in entries_today:
                    dep = e.get("origin") or ""
                    arr = e.get("destination") or ""
                    rpt = _format_time(e.get("rpt"))
                    sta = _format_time(e.get("sta"))
                    std = _format_time(e.get("std"))

                    duty_h, duty_m = _split_duration(e.get("duty_time"))
                    flight_h, flight_m = _split_duration(e.get("flight_time"))

                    if dep == "SIN":
                        e_col, f_col = rpt, sta
                        g_col, h_col = "", ""
                    else:
                        e_col, f_col = "", ""
                        g_col, h_col = std, sta

                    rows.append([
                        date_str, dep, arr, "Turnaround",
                        e_col, f_col, g_col, h_col,
                        duty_h, duty_m, "",
                        flight_h, flight_m
                    ])

            elif entries_today:
                e = entries_today[0]
                dep = e.get("origin") or ""
                arr = e.get("destination") or ""
                rpt = _format_time(e.get("rpt"))
                sta = _format_time(e.get("sta"))

                duty_h, duty_m = _split_duration(e.get("duty_time"))
                flight_h, flight_m = _split_duration(e.get("flight_time"))

                if dep == "SIN":
                    if _is_overnight(e):
                        # Departure day
                        rows.append([
                            date_str, dep, arr, "Layover",
                            rpt, "-", "", "",
                            "", "", "",
                            "", ""
                        ])

                        # Arrival next day
                        arrival = (d + datetime.timedelta(days=1)).strftime("%m/%d/%Y")

                        duty_h, duty_m = _split_duration(e.get("duty_time"))
                        flight_h, flight_m = _split_duration(e.get("flight_time"))

                        rows.append([
                            arrival, "", arr, "Layover",
                            "", sta, "", "",
                            duty_h, duty_m, "",
                            flight_h, flight_m
                        ])

                    else:
                        rows.append([
                            date_str, dep, arr, "Layover",
                            rpt, sta, "", "",
                            "", "", "",
                            "", ""
                        ])

                elif arr == "SIN":
                    if _is_overnight(e):
                        # departure day
                        rows.append([
                            date_str, "", station, "Layover",
                            "", "", rpt, "",
                            duty_h, duty_m, "",
                            flight_h, flight_m
                        ])

                        # arrival day
                        arrival = (d + datetime.timedelta(days=1)).strftime("%m/%d/%Y")
                        rows.append([
                            arrival, dep, arr, "Layover",
                            "", "-", "", sta,
                            "", "", "",
                            "", ""
                        ])
                    else:
                        rows.append([
                            date_str, dep, arr, "Layover",
                            "", "", rpt, sta,
                            duty_h, duty_m, "",
                            flight_h, flight_m
                        ])

            else:
                # pure layover day
                rows.append([
                    date_str, "", station, "Layover",
                    "", "", "", "",
                    "", "", "",
                    "", ""
                ])
        # --- Populate I–M only on first and last row of this trip ---
        if rows:
            trip_rows = rows[-len(all_dates):]  # rows just added for this trip

            # first flight of trip
            first_flight = fly[0]
            duty_h, duty_m = _split_duration(first_flight.get("duty_time"))
            flight_h, flight_m = _split_duration(first_flight.get("flight_time"))

            trip_rows[0][8] = duty_h
            trip_rows[0][9] = duty_m
            trip_rows[0][11] = flight_h
            trip_rows[0][12] = flight_m

            # last flight of trip (if different)
            last_flight = fly[-1]
            duty_h, duty_m = _split_duration(last_flight.get("duty_time"))
            flight_h, flight_m = _split_duration(last_flight.get("flight_time"))

            trip_rows[-1][8] = duty_h
            trip_rows[-1][9] = duty_m
            trip_rows[-1][11] = flight_h
            trip_rows[-1][12] = flight_m
    return rows


def _format_time(t):
    if not t:
        return ""
    return f"{t[:2]}:{t[2:]}"