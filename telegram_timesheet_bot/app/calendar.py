import os, json, base64, datetime
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_client():
    creds_b64 = os.getenv("GOOGLE_CREDS_B64")

    missing_padding = len(creds_b64) % 4
    if missing_padding:
        creds_b64 += "=" * (4 - missing_padding)

    creds_dict = json.loads(base64.b64decode(creds_b64).decode("utf-8"))

    creds = Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )

    return build("calendar", "v3", credentials=creds)


def push_events(trips):

    service = get_client()
    calendar_id = os.getenv("CALENDAR_ID", "primary")

    for trip in trips:

        first = trip[0]

        # =========================
        # 1. SS DUTY (standalone)
        # =========================
        if first.duty_type and first.duty_type.startswith("SS"):
            start = _build_dt(first, use_rpt=True)
            end = _build_dt(first, is_end=True)

            if not start or not end:
                continue

            event = {
                "summary": f"{first.duty_type} Duty",
                "location": "SIN",
                "description": f"{first.duty_type} Standby",
                "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Singapore"},
                "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Singapore"},
            }

            service.events().insert(calendarId=calendar_id, body=event).execute()
            continue

        # =========================
        # 2. STBY (inside trip)
        # =========================
        stby_entries = [e for e in trip if e.duty_type == "STBY"]

        for s in stby_entries:
            start = _build_dt(s, use_rpt=True)
            end = _build_dt(s, is_end=True)

            if not start or not end:
                continue

            event = {
                "summary": f"STBY ({s.sector})",
                "location": s.sector or "Unknown",
                "description": "Overseas Standby",
                "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Singapore"},
                "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Singapore"},
            }

            service.events().insert(calendarId=calendar_id, body=event).execute()

        # =========================
        # 3. FLY (existing logic)
        # =========================
        fly = [e for e in trip if e.duty_type == "FLY"]
        if not fly:
            continue

        outbound = next((f for f in fly if f.origin == "SIN"), None)
        inbound = next((f for f in reversed(fly) if f.destination == "SIN"), None)

        if not outbound or not inbound:
            continue

        start = _build_dt(outbound, use_rpt=True)
        end = _build_dt(inbound, is_end=True)

        event = {
            "summary": f"{outbound.destination} Trip",
            "location": outbound.destination,
            "description": f"{fly[0].flight_number} {fly[0].sector} - {fly[-1].flight_number} {fly[-1].sector}",
            "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Singapore"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Singapore"},
        }

        try:
            service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
        except Exception as e:
            if "already exists" in str(e):
                continue
            raise


def _build_dt(flight, is_end=False, use_rpt=False):

    date = datetime.datetime.strptime(flight.start_date, "%d%b%y")

    if is_end:
        time = flight.sta
    elif use_rpt:
        time = flight.rpt
    else:
        time = flight.std  # fallback only if you REALLY want

    if not time:
        return None

    dt = datetime.datetime(
        date.year, date.month, date.day,
        int(time[:2]), int(time[2:])
    )

    # overnight arrival fix
    if is_end and flight.rpt and flight.sta:
        if int(flight.sta) < int(flight.rpt):
            dt += datetime.timedelta(days=1)

    return dt