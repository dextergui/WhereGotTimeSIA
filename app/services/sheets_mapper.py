from typing import List
from app.models import FlightRow
from app.services.timesheet_parser import (
    group_trips,
    _parse_date_str,
    _format_time,
    _split_duration,
    _decimal_hours
)


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

        for idx, e in enumerate(trip):

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

            # Determine if we should put hours on this row
            should_put_hours = False
            is_intermediate_flight_row = False
            if e.duty_type == "FLY":
                leg_indices = [
                    i for i, other in enumerate(trip)
                    if other.duty_type == "FLY"
                    and other.flight_number == e.flight_number
                    and other.sector == e.sector
                ]
                is_outbound = (e.origin == "SIN" or e.destination != "SIN")
                if is_outbound:
                    should_put_hours = (idx == leg_indices[0])
                else:
                    should_put_hours = (idx == leg_indices[-1])

                if len(leg_indices) > 2:
                    is_intermediate_flight_row = leg_indices[0] < idx < leg_indices[-1]

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

                        # Log hours only on the designated row of the flight leg
                        duty_time=e.duty_time if should_put_hours else "",
                        flight_time=e.flight_time if should_put_hours else "",
                    )
                )

                continue

            # =====================================================
            # NORMAL FLIGHT ROW
            # =====================================================

            # OUTBOUND FLIGHT
            if is_outbound:

                if is_intermediate_flight_row:
                    ex_sin_sta = "-"
                    ex_sin_rpt = "-"
                else:
                    if e.rpt:
                        ex_sin_rpt = _format_time(e.rpt)

                    if e.sta:
                        ex_sin_sta = _format_time(e.sta)
                    else:
                        ex_sin_sta = "-"

            # INBOUND FLIGHT
            else:

                if is_intermediate_flight_row:
                    ex_sin_sta = "-"
                    ex_stn_rpt = "-"
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
