"""Timesheet processing service.
Parsing and processing logic for extracting structured data from timesheet images, and appending to Google Sheets.
"""

import datetime
import re
from typing import List, Dict
from app.models import FlightRow

OFF_DUTY_REGEX_STR = r"^(ATDO|AALV|OFFD)$"
STANDBY_DUTY_REGEX_STR = r"(SS\d+)|(STBY)"
LAYOVER_REGEX_STR = r"\bLO\b"
TIMES_REGEX_STR = r"\b\d{4}\b"
DURATIONS_REGEX_STR = r"\b\d{2}\s?:\s?\d{2}\b"
FLIGHT_NUMBER_REGEX_STR = r"(SQ\s?\d+)"
SECTOR_REGEX_STR = r"([A-Z]{3})\s?-\s?([A-Z]{3})"
SINGLE_SECTOR_REGEX_STR = r"\b[A-Z]{3}\b"

def _parse_date_str(date_str: str) -> datetime.date:
    """Convert '01Mar26' → datetime.date(2026,3,1)"""
    return datetime.datetime.strptime(date_str, "%d%b%y").date()

def _format_time(t):
    if not t:
        return ""
    return f"{t[:2]}:{t[2:]}"

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
    date_pattern = re.compile(r"\d{2}\W?[A-Za-z]{3}\W?\d{2}")

    # Initialize list of FlightRow
    entries: List[FlightRow] = []
    current_date = None

    for line in lines:
        date_match = date_pattern.search(line)

        if date_match:
            current_date = date_match.group().replace(" ", "")

        if not current_date:
            continue

        prev = entries[-1] if entries else None
        entry = _parse_row(current_date, line, prev)
        if entry:
            entries.append(entry)

    return {
        "entries": entries,
        "raw_text": text
    }


def _parse_row(date: str, line: str, prev: FlightRow | None) -> FlightRow | None:

    # Ignore header rows
    if "Start Day Flight" in line or "Date Number Duty" in line:
        return None

    # Standby Duties (SS50, SS20, ..., STBY)
    ss_match = re.search(STANDBY_DUTY_REGEX_STR, line)
    if ss_match:
        times = re.findall(TIMES_REGEX_STR, line)
        durations = re.findall(DURATIONS_REGEX_STR, line)
        sector = re.findall(SINGLE_SECTOR_REGEX_STR, line)
        return FlightRow(
            start_date = date,
            flight_number = None,
            sector = sector[0] if sector[0] == 'SIN' else prev.sector if prev and (prev.sector != 'SIN' or prev.destination != 'SIN') else None,
            origin = None,
            destination = None,
            duty_type = ss_match.group(),
            rpt = times[0] if len(times) >= 1 else None,
            std = times[1] if len(times) >= 2 else None,
            sta = times[2] if len(times) >= 3 else None,
            duty_time = durations[0] if len(durations) >= 1 else None,
            fdp = durations[1] if len(durations) >= 2 else None,
        )

    # Off duty (ATDO, AALV, OFFD)
    off_match = re.search(OFF_DUTY_REGEX_STR, line)
    if off_match:
        return FlightRow(
            start_date = date,
            flight_number = None,
            sector = 'SIN',
            origin = None,
            destination = None,
            duty_type = off_match.group(),
        )
    
    # Layover days
    lo_match = re.search(LAYOVER_REGEX_STR, line)
    if lo_match:
        country = re.search(SINGLE_SECTOR_REGEX_STR, line)
        return FlightRow(
            start_date = date,
            flight_number = None,
            sector = country.group() if country else None,
            origin = None,
            destination = None,
            duty_type = "LO",
        )

    # Flight Duty
    flight_match = re.search(FLIGHT_NUMBER_REGEX_STR, line)
    sector_match = re.search(SECTOR_REGEX_STR, line)

    if not flight_match or not sector_match:
        return None

    flight_number = flight_match.group().replace(" ", "")
    origin, destination = sector_match.groups()

    same_flight_as_prev = (
        prev
        and prev.duty_type != "LO"
        and prev.flight_number == flight_number
        and prev.sector == f"{origin}-{destination}"
    )

    is_turnaround = (
        prev
        and prev.duty_type == "FLY"
        and prev.flight_number
        and flight_number
        and prev.origin == destination
        and prev.destination == origin
        and prev.start_date == date
    )

    times = re.findall(TIMES_REGEX_STR, line)
    durations = re.findall(DURATIONS_REGEX_STR, line)

    rpt = std = sta = None
    flight_time = duty_time = fdp = None

    # All 3 times present: RPT, STD, STA
    if len(times) >= 3:
        rpt, std, sta = times[:3]

    # Only 2 times present
    elif len(times) == 2:
        # If same flight as previous and previous has RPT but no STD, this must be STD.
        if same_flight_as_prev:
            if prev.rpt and not prev.std:
                std, sta = times
        # If turnaround, the two times are STD + STA
        elif is_turnaround:
            std, sta = times
        # Flights with 2 times, these are usually RPT + STD 
        # e.g. overnight outbound with missing STA
        elif origin == "SIN":
            rpt, std = times
        # default case: likely RPT + STD with missing STA (first entry of overnight)
        else:
            rpt, std = times

    # Only 1 time present
    elif len(times) == 1:
        # If same flight as previous, likely the missing STA for an overnight continuation.
        if same_flight_as_prev:
            if not prev.sta:
                sta = times[0]
        # If not same flight as previous and is turnaround,
        # likely std for turnaround overnight departure
        elif is_turnaround:
            std = times[0]
        # If destination is SIN then likely STA (e.g. broken inbound with missing RPT/STD)
        elif destination == "SIN":
            sta = times[0]
        # Likely RPT with next day departure
        else:
            rpt = times[0]

    # All durations present: flight time, duty time, FDP
    if len(durations) >= 3:
        flight_time, duty_time, fdp = durations

    # Only 2 durations present
    elif len(durations) == 2:
        duty_time, fdp = durations
    
    # Only 1 duration present
    elif len(durations) == 1:
        # overnight continuation
        if same_flight_as_prev:
            fdp = durations[0]
        # turnaround with missing duty time
        elif is_turnaround:
            flight_time = durations[0]
        elif len(times) == 1 and sta:
            # likely duty time for an overnight with only STA (e.g. broken inbound)
            fdp = durations[0]
        else:
            # normal single-duration row
            flight_time = durations[0]

    return FlightRow(
        start_date = date,
        flight_number = flight_number,
        sector = f"{origin}-{destination}",
        origin = origin,
        destination = destination,
        duty_type = "FLY",
        rpt = rpt,
        std = std,
        sta = sta,
        flight_time = flight_time,
        duty_time = duty_time,
        fdp = fdp,
        raw_block = line
    )


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


def _decimal_hours(h, m):
    if not h or not m:
        return ""
    return round(int(h) + int(m)/60, 2)

def trips_to_sheet_rows(trips: list[list[dict]]) -> list[list]:
    rows = []

    for trip in trips:
        fly = [e for e in trip if e.get("duty_type") == "FLY"]
        if not fly:
            continue

        # --- Broken inbound from previous month ---
        if (
            len(fly) == 1
            and fly[0].get("origin") != "SIN"
            and fly[0].get("destination") == "SIN"
        ):
            e = fly[0]

            date_str = _parse_date_str(e["start_date"]).strftime("%m/%d/%Y")

            duty_h, duty_m = _split_duration(e.get("duty_time"))
            flight_h, flight_m = _split_duration(e.get("flight_time"))

            rows.append([
                date_str,
                e.get("origin") or "",
                e.get("destination") or "",
                "Layover",
                "", "-", "", _format_time(e.get("sta")),
                duty_h,
                duty_m,
                _decimal_hours(duty_h, duty_m),
                flight_h,
                flight_m
            ])

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

        all_dates = [
            start_date + datetime.timedelta(days=i)
            for i in range(days_span)
        ]
        added_dates = set()

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
                        duty_h, duty_m, _decimal_hours(duty_h, duty_m),
                        flight_h, flight_m
                    ])
                    added_dates.add(date_str)

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
                        added_dates.add(date_str)

                        # Arrival next day
                        arrival = (d + datetime.timedelta(days=1)).strftime("%m/%d/%Y")

                        duty_h, duty_m = _split_duration(e.get("duty_time"))
                        flight_h, flight_m = _split_duration(e.get("flight_time"))

                        rows.append([
                            arrival, "", arr, "Layover",
                            "", sta, "", "",
                            duty_h, duty_m, _decimal_hours(duty_h, duty_m),
                            flight_h, flight_m
                        ])
                        added_dates.add(arrival)

                    else:
                        rows.append([
                            date_str, dep, arr, "Layover",
                            rpt, sta, "", "",
                            "", "", "",
                            "", ""
                        ])
                        added_dates.add(date_str)

                elif arr == "SIN":
                    if _is_overnight(e):
                        # departure day
                        rows.append([
                            date_str, "", station, "Layover",
                            "", "", rpt, "",
                            duty_h, duty_m, _decimal_hours(duty_h, duty_m),
                            flight_h, flight_m
                        ])
                        added_dates.add(date_str)

                        # arrival day
                        arrival = (d + datetime.timedelta(days=1)).strftime("%m/%d/%Y")
                        rows.append([
                            arrival, dep, arr, "Layover",
                            "", "-", "", sta,
                            "", "", "",
                            "", ""
                        ])
                        added_dates.add(arrival)
                    else:
                        rows.append([
                            date_str, dep, arr, "Layover",
                            "", "", rpt, sta,
                            duty_h, duty_m, _decimal_hours(duty_h, duty_m),
                            flight_h, flight_m
                        ])
                        added_dates.add(date_str)

            else:
                # Skip days already added as part of overnight handling
                if date_str in added_dates:
                    continue
                # pure layover day
                rows.append([
                    date_str, "", station, "Layover",
                    "", "", "", "",
                    "", "", "",
                    "", ""
                ])
        # --- Populate I–M only on first and last row of this trip ---
        if rows:
            trip_rows = rows[trip_start_index:]

            if trip_rows:
                # wipe duty/flight columns for entire trip
                for r in trip_rows:
                    r[8] = ""
                    r[9] = ""
                    r[10] = ""
                    r[11] = ""
                    r[12] = ""

                # first actual flight row (departure)
                first_row = trip_rows[0]

                first_flight = fly[0]
                duty_h, duty_m = _split_duration(first_flight.get("duty_time"))
                flight_h, flight_m = _split_duration(first_flight.get("flight_time"))

                first_row[8] = duty_h
                first_row[9] = duty_m
                first_row[10] = _decimal_hours(duty_h, duty_m)
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
                        row[10] = _decimal_hours(duty_h, duty_m)
                        row[11] = flight_h
                        row[12] = flight_m
                        break
    return rows
