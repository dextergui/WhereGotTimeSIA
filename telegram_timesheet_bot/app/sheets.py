"""Google Sheets appender using service account credentials."""
from __future__ import annotations
import os
import json
from typing import List

import gspread

GOOGLE_CREDS_B64 = os.getenv("GOOGLE_CREDS_B64")


def _get_client():
    if GOOGLE_CREDS_B64:
        try:
            import base64

            try:
                creds_dict = json.loads(base64.b64decode(GOOGLE_CREDS_B64).decode("utf-8"))
            except Exception:
                creds_dict = json.loads(GOOGLE_CREDS_B64)
            return gspread.service_account_from_dict(creds_dict)
        except Exception as e:
            raise
    # If GOOGLE_APPLICATION_CREDENTIALS is set, gspread will pick it up
    return gspread.service_account()


def append_row(sheet_id: str, values: List[str], sheet_name: str | None = None):
    """Append a row to the given Google Sheet.

    If `sheet_name` is provided, it will try to open that worksheet by title.
    If the worksheet doesn't exist, it will be created. If `sheet_name` is None,
    the first worksheet (`sheet1`) is used.
    """
    client = _get_client()
    sh = client.open_by_key(sheet_id)
    if sheet_name:
        try:
            ws = sh.worksheet(sheet_name)
        except Exception:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
    else:
        ws = sh.sheet1
    ws.append_row(values)
