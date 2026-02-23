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
    date_pattern = re.compile(r"\d{2}[A-Za-z]{3}\d{2}")

    entries = []
    current_date = None

    for line in lines:
        date_match = date_pattern.search(line)

        if date_match:
            current_date = date_match.group()

        if not current_date:
            continue

        prev = entries[-1] if entries else None
        entry = _parse_row(current_date, line, prev)
        if entry:
            entries.append(entry)

    entries = merge_split_flights(entries)
    entries = fix_misplaced_overnight_departures(entries)
    # for e in entries:
    #     print(f"{e.get('start_date')} | {e.get('arrival_date')} | {e.get('flight_number')} | {e.get('sector')} | {e.get('duty_type')} | {e.get('rpt')} | {e.get('std')} | {e.get('sta')} | {e.get('flight_time')} | {e.get('duty_time')} | {e.get('fdp')} | ")

    return {
        "entries": entries,
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


def _parse_row(date: str, line: str, prev: dict | None) -> dict | None:

    # Ignore header rows
    if "Start Day Flight" in line:
        return None

    # Standby
    ss_match = re.search(r"(SS\d+)", line)
    if ss_match:
        times = re.findall(r"\b\d{4}\b", line)
        return {
            "start_date": date,
            "flight_number": None,
            "sector": None,
            "origin": None,
            "destination": None,
            "duty_type": ss_match.group(),
            "rpt": times[0] if len(times) >= 1 else None,
            "std": None,
            "sta": times[2] if len(times) >= 3 else None,
        }

    # Home duty (ATDO, AALV, OFFD)
    home_match = HOME_DUTY_REGEX.search(line)
    if home_match:
        return {
            "start_date": date,
            "flight_number": None,
            "sector": None,
            "origin": None,
            "destination": None,
            "duty_type": home_match.group(),
        }

    # Flight
    flight_match = re.search(r"(SQ\s?\d+)", line)
    sector_match = re.search(r"([A-Z]{3})\s?-\s?([A-Z]{3})", line)

    if not flight_match or not sector_match:
        return None

    flight_number = flight_match.group().replace(" ", "")
    origin, destination = sector_match.groups()

    same_flight_as_prev = (
        prev
        and prev.get("flight_number") == flight_number
        and prev.get("sector") == f"{origin}-{destination}"
    )

    times = re.findall(r"\b\d{4}\b", line)
    durations = re.findall(r"\b\d{2}:\d{2}\b", line)

    rpt = std = sta = None

    if len(times) >= 3:
        rpt, std, sta = times[:3]
    elif len(times) == 2:
        if same_flight_as_prev:
            if prev.get("rpt"):
                std, sta = times
        elif origin == "SIN":
            rpt, std = times
        elif len(durations) >= 2:
            rpt, std = times
        else:
            std, sta = times
    elif len(times) == 1:
        if same_flight_as_prev:
            if not prev.get("sta"):
                sta = times[0]
            elif not prev.get("std"):
                std = times[0]
        else:
            # broken inbound from previous month
            if origin != "SIN":
                sta = times[0]
            # outbound with only rpt
            else:
                rpt = times[0]

    flight_time = duty_time = fdp = None

    if len(durations) >= 3:
        flight_time, duty_time, fdp = durations[:3]
    elif len(durations) == 2:
        duty_time, fdp = durations
    elif len(durations) == 1:
        if same_flight_as_prev:
            # overnight continuation
            fdp = durations[0]

        elif len(times) == 1 and origin != "SIN":
            # broken inbound from previous month
            # single time = STA, single duration = FDP
            fdp = durations[0]

        else:
            # normal single-duration row
            flight_time = durations[0]

    return {
        "start_date": date,
        "flight_number": flight_number,
        "sector": f"{origin}-{destination}",
        "origin": origin,
        "destination": destination,
        "duty_type": "FLY",
        "rpt": rpt,
        "std": std,
        "sta": sta,
        "flight_time": flight_time,
        "duty_time": duty_time,
        "fdp": fdp,
        "raw_block": line
    }


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

    return _parse_date_str(arrival_date).strftime("%d%b%y")


def trips_to_message(trips: list[list[dict]]) -> str:
    if not trips or not trips[0]:
        return "No trips found."

    first_date = _parse_date_str(trips[0][0]["start_date"])
    month_name = first_date.strftime("%B").upper()

    lines = [f"Flights for *{month_name} {first_date.year}*:"]

    for trip in trips:
        if not trip:
            continue
        e0 = trip[0]
        start = _parse_date_str(e0["start_date"]).strftime("%d%b")

        # Standby
        if e0.get("duty_type", "").startswith("SS"):
            end = _parse_date_str(trip[-1]["start_date"]).strftime("%d%b")
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
        end = _parse_date_str(_trip_end_date(trip)).strftime("%d%b")

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

        trip_start_index = len(rows)
        start_date = _parse_date_str(fly[0]["start_date"])
        last = fly[-1]
        end_date = _parse_date_str(last["start_date"])

        # If last flight has arrival_date, use it to compute end_date (accounts for overnight inbound)
        if last.get("arrival_date"):
            end_date = _parse_date_str(last["arrival_date"])

            # prevent duplicate arrival day
            last_is_overnight_inbound = (
                last.get("destination") == "SIN"
                and _is_overnight(last)
            )
        else:
            last_is_overnight_inbound = False

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

        days_span = (end_date - start_date).days + 1

        if last_is_overnight_inbound:
            days_span -= 1  # prevent duplicate last day

        all_dates = [
            start_date + datetime.timedelta(days=i)
            for i in range(days_span)
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
                        duty_h, duty_m, "=ROUND(I{row}+(J{row}/60), 2)",
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
                            "", "", "=ROUND(I{row}+(J{row}/60), 2)",
                            "", ""
                        ])

                        # Arrival next day
                        arrival = (d + datetime.timedelta(days=1)).strftime("%m/%d/%Y")

                        duty_h, duty_m = _split_duration(e.get("duty_time"))
                        flight_h, flight_m = _split_duration(e.get("flight_time"))

                        rows.append([
                            arrival, "", arr, "Layover",
                            "", sta, "", "",
                            duty_h, duty_m, "=ROUND(I{row}+(J{row}/60), 2)",
                            flight_h, flight_m
                        ])

                    else:
                        rows.append([
                            date_str, dep, arr, "Layover",
                            rpt, sta, "", "",
                            "", "", "=ROUND(I{row}+(J{row}/60), 2)",
                            "", ""
                        ])

                elif arr == "SIN":
                    if _is_overnight(e):
                        # departure day
                        rows.append([
                            date_str, "", station, "Layover",
                            "", "", rpt, "",
                            duty_h, duty_m, "=ROUND(I{row}+(J{row}/60), 2)",
                            flight_h, flight_m
                        ])

                        # arrival day
                        arrival = (d + datetime.timedelta(days=1)).strftime("%m/%d/%Y")
                        rows.append([
                            arrival, dep, arr, "Layover",
                            "", "-", "", sta,
                            "", "", "=ROUND(I{row}+(J{row}/60), 2)",
                            "", ""
                        ])
                    else:
                        rows.append([
                            date_str, dep, arr, "Layover",
                            "", "", rpt, sta,
                            duty_h, duty_m, "=ROUND(I{row}+(J{row}/60), 2)",
                            flight_h, flight_m
                        ])

            else:
                # pure layover day
                rows.append([
                    date_str, "", station, "Layover",
                    "", "", "", "",
                    "", "", "=ROUND(I{row}+(J{row}/60), 2)",
                    "", ""
                ])
        # --- Populate I–M only on first and last row of this trip ---
        if rows:
            trip_rows = rows[trip_start_index:]

            if trip_rows:

                # first actual flight row (departure)
                first_row = trip_rows[0]

                first_flight = fly[0]
                duty_h, duty_m = _split_duration(first_flight.get("duty_time"))
                flight_h, flight_m = _split_duration(first_flight.get("flight_time"))

                first_row[8] = duty_h
                first_row[9] = duty_m
                first_row[11] = flight_h
                first_row[12] = flight_m

                # find actual arrival row for last flight
                last_flight = fly[-1]
                duty_h, duty_m = _split_duration(last_flight.get("duty_time"))
                flight_h, flight_m = _split_duration(last_flight.get("flight_time"))

                # arrival row = last row that has arrival airport
                for row in reversed(trip_rows):
                    if row[2] == last_flight.get("destination"):
                        row[8] = duty_h
                        row[9] = duty_m
                        row[11] = flight_h
                        row[12] = flight_m
                        break
    return rows


def _format_time(t):
    if not t:
        return ""
    return f"{t[:2]}:{t[2:]}"