import datetime
import re
import calendar


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
