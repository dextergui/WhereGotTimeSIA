"""Timesheet processing service.
Parsing and processing logic for extracting structured data from timesheet images, and appending to Google Sheets.
"""

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

def trips_to_message(entries: List[FlightRow]) -> str:
    trips = group_trips(entries)

    if not trips:
        return "No trips found."

    first_date = _parse_date_str(trips[0][0].start_date)
    month_name = first_date.strftime("%B")

    lines = [f"Flights for {month_name} {first_date.year}", "="*35]

    for trip in trips:
        fly = [e for e in trip if e.duty_type == "FLY"]
        stby = [e for e in trip if e.duty_type == "STBY"]
        singaporeStby = [e for e in trip if e.duty_type.startswith("SS")]

        # Handle singapore standby (e.g. SS22 / SS60)
        if not fly and singaporeStby:
            s = singaporeStby[0]
            d = _parse_date_str(s.start_date)

            lines.append(f"\n{d.strftime('%d %b')}")

            rpt = f"{d.day}/{d.month} {_format_time(s.rpt)}" if s.rpt else "-"
            sta = f"{d.day}/{d.month} {_format_time(s.sta)}" if s.sta else "-"

            lines.append(f"{s.sector} ({s.duty_type}) | {rpt} | {sta}")
            continue

        if not fly:
            continue

        start = _parse_date_str(fly[0].start_date)
        end = _parse_date_str(fly[-1].start_date)

        lines.append(f"\n{start.strftime('%d %b')} - {end.strftime('%d %b')}")

        fly = _merge_flight_legs(fly)
        # --- PRINT ALL FLIGHT LEGS ---
        for f in fly:
            dep = f.origin
            arr = f.destination

            rpt_date = _parse_date_str(f.start_date)
            sta_date = rpt_date

            # overnight arrival
            if f.sta and f.rpt and int(f.sta) < int(f.rpt):
                sta_date += datetime.timedelta(days=1)

            rpt_str = f"{rpt_date.day}/{rpt_date.month} {_format_time(f.rpt)}" if f.rpt else "-"
            sta_str = f"{sta_date.day}/{sta_date.month} {_format_time(f.sta)}" if f.sta else "-"

            lines.append(
                f"{dep} → {arr} | {f.flight_number} | {rpt_str} | {sta_str}"
            )

        # --- STANDBY ---
        for s_start, s_end in _merge_stby(stby):
            d1 = _parse_date_str(s_start.start_date)
            d2 = _parse_date_str(s_end.start_date)

            rpt = f"{d1.day}/{d1.month} {_format_time(s_start.rpt)}" if s_start.rpt else "-"
            sta = f"{d2.day}/{d2.month} {_format_time(s_end.rpt)}" if s_end.rpt else "-"

            lines.append(f"{s_start.sector} (STBY) | {rpt} | {sta}")

    return "\n".join(lines)

def _make_sheet_row(
    date_str,
    dep="",
    arr="",
    trip_type="Layover",
    ex_sin_rpt="",
    ex_sin_sta="",
    ex_stn_rpt="",
    ex_stn_sta="",
    duty_time="",
    flight_time=""
):
    duty_h, duty_m = _split_duration(duty_time)
    flight_h, flight_m = _split_duration(flight_time)

    return [
        date_str,
        dep,
        arr,
        trip_type,
        ex_sin_rpt,
        ex_sin_sta,
        ex_stn_rpt,
        ex_stn_sta,
        duty_h,
        duty_m,
        _decimal_hours(duty_h, duty_m) if duty_h else "",
        flight_h,
        flight_m,
        _decimal_hours(flight_h, flight_m) if flight_h else "",
    ]

def _is_empty_layover_row(row: list) -> bool:
    """
    True if this is a pure placeholder layover row.
    """

    dep = row[1]
    ex_sin_rpt = row[4]
    ex_sin_sta = row[5]
    ex_stn_rpt = row[6]
    ex_stn_sta = row[7]

    has_times = any([
        ex_sin_rpt,
        ex_sin_sta,
        ex_stn_rpt,
        ex_stn_sta,
    ])

    return dep == "" and not has_times

def trips_to_sheet_rows(entries: List[FlightRow]) -> list[list]:
    trips = group_trips(entries)
    rows = []

    for trip in trips:

        # Skip SS duties
        if trip[0].duty_type.startswith("SS"):
            continue

        for e in trip:

            date_str = _parse_date_str(e.start_date).strftime("%m/%d/%Y")

            # -----------------------------
            # LAYOVER ROW
            # -----------------------------
            if e.duty_type == "LO":
                rows.append(
                    _make_sheet_row(
                        date_str=date_str,
                        dep="",
                        arr=e.sector,
                        trip_type="Layover",
                    )
                )
                continue

            # Ignore standby rows for sheet
            if e.duty_type == "STBY":
                continue

            if e.duty_type != "FLY":
                continue

            dep = e.origin or ""
            arr = e.destination or ""

            ex_sin_rpt = ""
            ex_sin_sta = ""
            ex_stn_rpt = ""
            ex_stn_sta = ""

            is_continuation = e.sta and not e.rpt and not e.std
            is_outbound = dep == "SIN" or arr != "SIN"

            # =====================================================
            # CONTINUATION ROW
            # =====================================================

            if is_continuation:

                continuation_is_outbound = arr != "SIN"

                # outbound continuation
                # SIN-FRA -> next day FRA arrival
                if continuation_is_outbound:
                    dep = ""
                    arr = e.destination
                    ex_sin_sta = _format_time(e.sta)

                # inbound continuation
                # FRA-SIN -> next day SIN arrival
                else:
                    dep = e.origin
                    arr = "SIN"
                    ex_sin_sta = "-"
                    ex_stn_sta = _format_time(e.sta)

                rows.append(
                    _make_sheet_row(
                        date_str=date_str,
                        dep=dep,
                        arr=arr,
                        trip_type=e.trip_type,
                        ex_sin_sta=ex_sin_sta,
                        ex_stn_sta=ex_stn_sta,

                        # ONLY inbound continuation gets hours
                        duty_time=e.duty_time if not continuation_is_outbound else "",
                        flight_time=e.flight_time if not continuation_is_outbound else "",
                    )
                )

                continue

            # =====================================================
            # NORMAL FLIGHT ROW
            # =====================================================

            # OUTBOUND FLIGHT
            if is_outbound:

                if e.rpt:
                    ex_sin_rpt = _format_time(e.rpt)

                if e.sta:
                    ex_sin_sta = _format_time(e.sta)
                else:
                    ex_sin_sta = "-"

            # INBOUND FLIGHT
            else:

                # turnaround uses STD
                if e.trip_type == "Turnaround":
                    ex_stn_rpt = _format_time(e.std) if e.std else ""

                else:
                    ex_stn_rpt = _format_time(e.rpt) if e.rpt else ""

                if e.sta:
                    ex_stn_sta = _format_time(e.sta)


            # =====================================================
            # HOURS OWNERSHIP
            # =====================================================

            should_put_hours = True

            # if arr == "SIN" and not e.sta:
            #     # inbound overnight first row
            #     should_put_hours = False

            # outbound flights own hours on FIRST row
            if ex_sin_rpt == "" and ex_sin_sta != "" and ex_stn_rpt == "" and ex_stn_sta == "":
                should_put_hours = False
            # inbound overnight flights own hours on LAST row
            if ex_sin_rpt == "" and ex_sin_sta == "" and ex_stn_rpt != "" and ex_stn_sta == "":
                should_put_hours = False

            rows.append(
                _make_sheet_row(
                    date_str=date_str,
                    dep=dep,
                    arr=arr,
                    trip_type=e.trip_type,
                    ex_sin_rpt=ex_sin_rpt,
                    ex_sin_sta=ex_sin_sta,
                    ex_stn_rpt=ex_stn_rpt,
                    ex_stn_sta=ex_stn_sta,

                    duty_time=e.duty_time if should_put_hours else "",
                    flight_time=e.flight_time if should_put_hours else "",
                )
            )

    # =====================================================
    # REMOVE DUPLICATE PURE LAYOVER ROWS
    # Keep flight/continuation rows over empty layovers
    # =====================================================

    grouped = {}

    for row in rows:
        grouped.setdefault(row[0], []).append(row)

    final_rows = []

    for date, day_rows in grouped.items():

        # if there are flight/continuation rows,
        # remove empty layover placeholders
        has_non_empty = any(
            not _is_empty_layover_row(r)
            for r in day_rows
        )

        if has_non_empty:
            day_rows = [
                r for r in day_rows
                if not _is_empty_layover_row(r)
            ]

        final_rows.extend(day_rows)
        
    deduped = []
    seen = set()

    for row in final_rows:
        key = tuple(row)

        if key in seen:
            continue

        seen.add(key)
        deduped.append(row)

    return deduped

    # return final_rows


# Availability Mode Functions

def validate_extracted_block(text: str, expected_month=None, expected_year=None):

    try:
        parsed = parse_extracted_summary(text)
    except Exception:
        return False, "❌ Invalid summary block format."

    month = parsed["month"]
    year = parsed["year"]
    trips = parsed["trips"]

    if not trips:
        return False, "❌ No trips detected."

    # global constraint
    if expected_month and expected_year:
        if month != expected_month or year != expected_year:
            return False, f"❌ Trips must be in {expected_month}/{expected_year}"

    return True, parsed

def parse_extracted_summary(text: str):

    header = re.search(r"Flights\s+for\s+([A-Z]+)\s+(\d{4})", text)
    if not header:
        raise ValueError("Invalid header")

    month_name = header.group(1)
    year = int(header.group(2))

    month = datetime.datetime.strptime(month_name, "%B").month

    lines = text.splitlines()

    trips = []

    for line in lines:

        line = line.strip()
        if "|" not in line:
            continue

        # example:
        # 01Mar - 03Mar | NRT | 09:00 (SQ12) | 18:00 (SQ11)

        parts = [p.strip() for p in line.split("|")]

        if len(parts) < 4:
            continue

        date_part = parts[0]
        location = parts[1]

        m = re.match(r"(\d{2})([A-Za-z]{3})\s*-\s*(\d{2})([A-Za-z]{3})", date_part)
        if not m:
            continue

        start_day = int(m.group(1))
        end_day = int(m.group(3))

        rpt_time = re.search(r"(\d{2}:\d{2})", parts[2])
        sta_time = re.search(r"(\d{2}:\d{2})", parts[3])

        if not rpt_time or not sta_time:
            continue

        start_dt = datetime.datetime(
            year, month, start_day,
            int(rpt_time.group(1)[:2]),
            int(rpt_time.group(1)[3:])
        )

        end_dt = datetime.datetime(
            year, month, end_day,
            int(sta_time.group(1)[:2]),
            int(sta_time.group(1)[3:])
        )

        trips.append({
            "start": start_dt,
            "end": end_dt,
            "location": location
        })

    return {
        "month": month,
        "year": year,
        "trips": trips
    }

def find_common_locations(people, month, year):

    slots = find_meeting_slots(people, month, year)

    if not slots:
        return "❌ No suitable meeting slots found."

    lines = ["⭐ Best Meeting Slots:\n"]

    for s in slots[:10]:

        names = ", ".join(s["people"])

        lines.append(
            f"{s['start'].strftime('%d %b %H:%M')} → "
            f"{s['end'].strftime('%d %b %H:%M')}\n"
            f"📍 {s['location']} | 👥 {names} \n"
        )

    return "\n".join(lines)

def find_meeting_slots(people, month, year, min_hours=3):

    overlaps = find_overlap_windows(people, month, year)

    merged = merge_overlaps(overlaps)

    candidates = []

    for start, end, loc, names in merged:

        duration = (end-start).total_seconds() / 3600

        if duration < min_hours:
            continue

        score = (
            len(names)*1000 +
            duration*10 +
            (200 if loc == "SIN" else 0)
        )

        candidates.append({
            "start": start,
            "end": end,
            "location": loc,
            "people": names,
            "duration": duration,
            "score": score
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    return candidates

def merge_overlaps(overlaps):

    overlaps.sort(key=lambda x: x[0])

    merged = []

    for o in overlaps:

        if not merged:
            merged.append(list(o))
            continue

        last = merged[-1]

        if (
            last[1] >= o[0] and
            last[2] == o[2] and
            last[3] == o[3]
        ):
            last[1] = o[1]
        else:
            merged.append(list(o))

    return merged

def find_overlap_windows(people, month, year):

    timelines = {}

    for p in people:
        timelines[p["name"]] = build_presence_from_summary(
            p["trips"], month, year
        )

    points = set()

    for tl in timelines.values():
        for s,e,_ in tl:
            points.add(s)
            points.add(e)

    points = sorted(points)

    overlaps = []

    for i in range(len(points)-1):

        seg_start = points[i]
        seg_end = points[i+1]

        location_groups = {}

        for name, tl in timelines.items():

            for s,e,loc in tl:
                if s <= seg_start and e >= seg_end:
                    location_groups.setdefault(loc, []).append(name)

        for loc, names in location_groups.items():
            if len(names) >= 2:
                overlaps.append((seg_start, seg_end, loc, tuple(sorted(names))))

    return overlaps

def build_presence_from_summary(trips, month, year):

    timeline = []

    month_start = datetime.datetime(year, month, 1)
    month_end = datetime.datetime(
        year, month,
        calendar.monthrange(year, month)[1],
        23, 59
    )

    current_time = month_start
    current_loc = "SIN"

    trips = sorted(trips, key=lambda x: x["start"])

    for i, t in enumerate(trips):

        # gap before trip → at current location
        if t["start"] > current_time:
            timeline.append((current_time, t["start"], current_loc))

        # during trip → overseas
        timeline.append((t["start"], t["end"], t["location"]))

        current_time = t["end"]

        # decide where crew is AFTER trip
        is_last_trip = (i == len(trips) - 1)

        if is_last_trip and t["location"] != "SIN":
            current_loc = t["location"]   # still overseas
        else:
            current_loc = "SIN"

    # tail after final trip
    if current_time < month_end:
        timeline.append((current_time, month_end, current_loc))

    return timeline