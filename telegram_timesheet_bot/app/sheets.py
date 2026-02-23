"""Google Sheets appender using service account credentials."""
from __future__ import annotations
import os
import json
import base64
from typing import List, Union

import gspread

def _get_client():
    creds_b64 = os.getenv("GOOGLE_CREDS_B64")
    if not creds_b64:
        raise RuntimeError("GOOGLE_CREDS_B64 not set")

    # Fix padding
    missing_padding = len(creds_b64) % 4
    if missing_padding:
        creds_b64 += "=" * (4 - missing_padding)

    try:
        creds_dict = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
    except Exception:
        creds_dict = json.loads(creds_b64)

    return gspread.service_account_from_dict(creds_dict)


def append_row(
    sheet_id: str,
    values: Union[List[str], List[List[str]]],
    sheet_name: str | None = None,
):
    """
    Append one row or multiple rows to Google Sheets.
    Accepts:
        - List[str]
        - List[List[str]]
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

    if not values:
        return

    ws.append_rows(
        values if isinstance(values[0], list) else [values],
        value_input_option="USER_ENTERED"
    )

