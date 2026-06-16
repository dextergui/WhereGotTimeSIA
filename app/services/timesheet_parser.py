import datetime
import re
import calendar
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


def _merge_flight_legs(fly: List[FlightRow]) -> List[FlightRow]:
    merged = []
    i = 0

    while i < len(fly):
        curr = fly[i]

        if (
            i + 1 < len(fly)
            and fly[i + 1].flight_number == curr.flight_number
            and fly[i + 1].sector == curr.sector
        ):
            nxt = fly[i + 1]

            merged.append(FlightRow(
                start_date=curr.start_date,
                flight_number=curr.flight_number,
                sector=curr.sector,
                origin=curr.origin,
                destination=curr.destination,
                duty_type="FLY",
                rpt=curr.rpt,
                std=curr.std,
                sta=nxt.sta,
                flight_time=curr.flight_time,
                duty_time=curr.duty_time,
                fdp=curr.fdp,
            ))
            i += 2
        else:
            merged.append(curr)
            i += 1

    return merged


def _merge_stby(stby: List[FlightRow]) -> List[tuple]:
    if not stby:
        return []

    merged = []
    i = 0

    while i < len(stby):
        start = stby[i]
        end = start

        while i + 1 < len(stby) and stby[i + 1].sector == start.sector:
            end = stby[i + 1]
            i += 1

        merged.append((start, end))
        i += 1

    return merged
