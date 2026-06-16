import datetime
from typing import List
from app.models import FlightRow
from app.services.timesheet_parser import (
    group_trips,
    _parse_date_str,
    _format_time,
    _merge_flight_legs,
    _merge_stby
)


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

            # overnight arrival fix
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
