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

INTERNATIONAL_US_AIRPORTS = {"IAH", "LAX", "JFK", "EWR", "SFO", "SEA"}

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

def _decimal_hours(h, m):
    if not h or not m:
        return ""
    return round(int(h) + int(m)/60, 2)

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
            # Restore flight_time & duty_time from previous overnight leg
            flight_time = prev.flight_time
            duty_time = prev.duty_time
        # turnaround with missing duty time
        elif is_turnaround:
            flight_time = durations[0]
        elif len(times) == 1 and sta:
            # likely duty time for an overnight with only STA (e.g. broken inbound)
            fdp = durations[0]
        else:
            # normal single-duration row
            flight_time = durations[0]

    # Inherit durations for overnight continuation with no durations
    if same_flight_as_prev and not durations:
        flight_time = prev.flight_time
        duty_time = prev.duty_time
        fdp = prev.fdp

    return FlightRow(
        start_date = date,
        flight_number = flight_number,
        sector = f"{origin}-{destination}",
        origin = origin,
        destination = destination,
        duty_type = "FLY",
        trip_type = "Layover",
        rpt = rpt,
        std = std,
        sta = sta,
        flight_time = flight_time,
        duty_time = duty_time,
        fdp = fdp,
        raw_block = line
    )

def categorize_trip(trips: list[list[FlightRow]]) -> list[list[FlightRow]]:
    for trip in trips:
        fly = [e for e in trip if e.duty_type == "FLY"]
        lo = [e for e in trip if e.duty_type == "LO"]

        if len(fly)>1:
            if not lo:
                for e in fly:
                    e.trip_type = "Turnaround"
            elif fly[0].destination in INTERNATIONAL_US_AIRPORTS:
                for e in fly:
                    e.trip_type = "Direct US"
    return trips

def group_trips(entries: list[FlightRow]) -> list[list[FlightRow]]:
    trips = []
    current = []

    for e in entries:
        if e.duty_type and e.duty_type.startswith("SS"):
            if current:
                trips.append(current)
                current = []
            trips.append([e])
            continue
        if e.duty_type == "STBY":
            current.append(e)
            continue

        if e.duty_type == "LO":
            current.append(e)
            continue

        if e.duty_type != "FLY":
            continue

        # Broken inbound at start of period
        if not current and e.origin != "SIN" and e.destination == "SIN":
            trips.append([e])
            continue

        # Start trip
        if not current and e.origin == "SIN":
            current = [e]
            continue

        if current:
            current.append(e)

            # End trip when inbound arrives SIN and STA exists
            if e.destination == "SIN" and e.sta:
                trips.append(current)
                current = []

    if current:
        trips.append(current)

    trips = categorize_trip(trips)
    return trips


def trips_to_message(entries: List[FlightRow]) -> str:

    trips = group_trips(entries)
    # for trip in trips:
    #     print("=== Trip ===")
    #     for e in trip:
    #         print(e)
    #     print("============")

    if not trips:
        return "No trips found."

    first_date = _parse_date_str(trips[0][0].start_date)
    month_name = first_date.strftime("%B").upper()

    lines = [f"Flights for {month_name} {first_date.year}:"]

    for trip in trips:
        first_entry = trip[0]
        start = _parse_date_str(first_entry.start_date).strftime("%d%b")

        # Singapore Standby
        if first_entry.duty_type.startswith("SS"):
            end = _parse_date_str(trip[-1].start_date).strftime("%d%b")
            lines.append(
                f"{start} - {end} | {first_entry.duty_type} | "
                f"{_format_time(first_entry.rpt)} | {_format_time(first_entry.sta)}"
            )
            continue

        fly = [e for e in trip if e.duty_type == "FLY"]
        stby = [e for e in trip if e.duty_type == "STBY"]

        if not fly:
            continue

        # Determine end date using last flight entry
        last_flight = fly[-1]
        end = _parse_date_str(last_flight.start_date).strftime("%d%b")

        # Broken inbound only
        if fly[0].origin != "SIN" and fly[0].destination == "SIN":
            if fly[0].rpt:
                row = f"{start} - {end} | {fly[0].sector} | "+f"{_format_time(fly[0].rpt)} ({fly[0].flight_number}) | "+f"{_format_time(fly[0].sta)} ({fly[0].flight_number})"
            else:
                row = f"{start} - {end} | {fly[0].sector} | - | "+f"{_format_time(fly[0].sta)} ({fly[0].flight_number})"
            lines.append(row)
            
        # Broken Outbound only
        elif fly[-1].destination != "SIN":
            if last_flight.sta:
                row = f"{start} - {end} | {fly[0].sector} | "+f"{_format_time(fly[0].rpt)} ({fly[0].flight_number}) | "+f"{_format_time(last_flight.sta)} ({last_flight.flight_number})"
            else:
                row = f"{start} - {end} | {fly[0].sector} | "+f"{_format_time(fly[0].rpt)} ({fly[0].flight_number}) | -"
            lines.append(row)
            
        else:

            outbound = next((e for e in fly if e.origin == "SIN"), None)
            inbound = next((e for e in reversed(fly) if e.destination == "SIN"), None)

            if outbound and inbound:
                lines.append(
                    f"{start} - {end} | {outbound.destination} | "
                    f"{_format_time(outbound.rpt)} ({outbound.flight_number}) | "
                    f"{_format_time(inbound.sta)} ({inbound.flight_number})"
                )

        # Overseas Standby (append AFTER trip)
        for s in stby:
            stby_date = _parse_date_str(s.start_date).strftime("%d%b")
            lines.append(
                f"{stby_date} - {stby_date} | STBY ({s.sector}) | "
                f"{_format_time(s.rpt)} | {_format_time(s.sta)}"
            )

    return "\n".join(lines)


def trips_to_sheet_rows(entries: List[FlightRow]) -> list[list]:
    trips = group_trips(entries)
    rows = []

    for trip in trips:
        trip_start_index = len(rows)

        # Skip SS standby
        if trip[0].duty_type.startswith("SS"):
            continue

        fly = [e for e in trip if e.duty_type == "FLY"]
        if not fly:
            continue

        is_turnaround_trip = all(f.trip_type == "Turnaround" for f in fly)

        start_date = _parse_date_str(fly[0].start_date)
        last_flight = fly[-1]

        # Determine end date (handle overnight arrival)
        end_date = _parse_date_str(last_flight.start_date)
        if last_flight.sta and last_flight.rpt and int(last_flight.sta) < int(last_flight.rpt):
            end_date += datetime.timedelta(days=1)

        days = (end_date - start_date).days + 1
        all_dates = [start_date + datetime.timedelta(days=i) for i in range(days)]

        station = fly[0].destination if fly[0].origin == "SIN" else fly[0].origin

        # Map flights by date
        flights_by_date = {}
        for f in fly:
            d = _parse_date_str(f.start_date)
            flights_by_date.setdefault(d, []).append(f)

        for d in all_dates:
            date_str = d.strftime("%m/%d/%Y")
            todays = flights_by_date.get(d, [])

            if is_turnaround_trip and todays:
                for f in todays:
                    dep = f.origin or ""
                    arr = f.destination or ""

                    ex_sin_rpt = _format_time(f.rpt) if dep == "SIN" else ""
                    if dep == "SIN":
                        if not f.sta and f.rpt:
                            # First row of overnight outbound
                            ex_sin_sta = "-"
                        else:
                            ex_sin_sta = _format_time(f.sta)
                    elif arr == "SIN" and (not f.rpt and not f.std):
                        # Second row of overnight inbound
                        ex_sin_sta = "-"
                    else:
                        ex_sin_sta = ""
                    ex_stn_rpt = _format_time(f.std if is_turnaround_trip else f.rpt) if arr == "SIN" else ""
                    ex_stn_sta = _format_time(f.sta) if arr == "SIN" else ""

                    duty_h, duty_m = _split_duration(f.duty_time)
                    flight_h, flight_m = _split_duration(f.flight_time)

                    rows.append([
                        date_str, dep, arr, f.trip_type,
                        ex_sin_rpt, ex_sin_sta,
                        ex_stn_rpt, ex_stn_sta,
                        duty_h, duty_m, _decimal_hours(duty_h, duty_m),
                        flight_h, flight_m, _decimal_hours(flight_h, flight_m)
                    ])
                continue

            if todays:
                f = todays[0]
                dep = f.origin or ""
                arr = f.destination or ""

                ex_sin_rpt = _format_time(f.rpt) if dep == "SIN" else ""
                if dep == "SIN":
                    if not f.sta and f.rpt:
                        # First row of overnight outbound
                        ex_sin_sta = "-"
                    else:
                        ex_sin_sta = _format_time(f.sta)
                elif arr == "SIN" and (not f.rpt and not f.std):
                    # Second row of overnight inbound
                    ex_sin_sta = "-"                        
                else:
                    ex_sin_sta = ""

                ex_stn_rpt = _format_time(f.rpt) if arr == "SIN" else ""
                ex_stn_sta = _format_time(f.sta) if arr == "SIN" else ""

                duty_h, duty_m = _split_duration(f.duty_time)
                flight_h, flight_m = _split_duration(f.flight_time)

                rows.append([
                    date_str, dep, arr, f.trip_type,
                    ex_sin_rpt, ex_sin_sta,
                    ex_stn_rpt, ex_stn_sta,
                    duty_h, duty_m, _decimal_hours(duty_h, duty_m),
                    flight_h, flight_m, _decimal_hours(flight_h, flight_m)
                ])
            else:
                # Pure layover day
                rows.append([
                    date_str, "", station, "Layover",
                    "", "", "", "",
                    "", "", 0.0,
                    "", "", 0
                ])
        # --- Post process this trip ---
        trip_rows = rows[trip_start_index:]
        if not trip_rows:
            continue

        first_row = next(r for r in trip_rows if r[1] == fly[0].origin)
        last_row = next(r for r in reversed(trip_rows) if r[2] == fly[-1].destination)

        # 1) Clear duty & flight times for ALL rows
        for r in trip_rows:
            r[8] = ""
            r[9] = ""
            r[10] = ""
            r[11] = ""
            r[12] = ""
            r[13] = ""

        # 2) Restore duty/flight only for first and last row
        first_flight = fly[0]
        last_flight = fly[-1]

        duty_h, duty_m = _split_duration(first_flight.duty_time)
        flight_h, flight_m = _split_duration(first_flight.flight_time)

        first_row[8] = duty_h
        first_row[9] = duty_m
        first_row[10] = _decimal_hours(duty_h, duty_m)
        first_row[11] = flight_h
        first_row[12] = flight_m
        first_row[13] = _decimal_hours(flight_h, flight_m)

        duty_h, duty_m = _split_duration(last_flight.duty_time)
        flight_h, flight_m = _split_duration(last_flight.flight_time)

        last_row[8] = duty_h
        last_row[9] = duty_m
        last_row[10] = _decimal_hours(duty_h, duty_m)
        last_row[11] = flight_h
        last_row[12] = flight_m
        last_row[13] = _decimal_hours(flight_h, flight_m)

        if not is_turnaround_trip and len(trip_rows) > 2 :
            # 3) Middle rows: only keep ARR as station country
            for r in trip_rows[1:-1]:
                r[1] = ""  # clear dep
                r[2] = first_row[2]  # keep arr

    return rows
