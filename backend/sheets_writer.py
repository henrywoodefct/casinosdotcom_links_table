from __future__ import annotations

from typing import Dict, List, Tuple
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import gspread
from google.oauth2.service_account import Credentials


# ─────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────

def _client_from_env() -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    key_json = os.environ.get("GSHEETS_KEY_JSON")
    key_path = os.environ.get("GSHEETS_KEY_PATH")

    if key_json:
        creds_dict = json.loads(key_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    elif key_path and Path(key_path).exists():
        creds = Credentials.from_service_account_file(key_path, scopes=scopes)
    else:
        raise RuntimeError(
            "Missing Google Sheets credentials. "
            "Set GSHEETS_KEY_JSON (preferred) or GSHEETS_KEY_PATH."
        )

    return gspread.authorize(creds)


def _ensure_worksheet(sh, title: str) -> gspread.Worksheet:
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=200)


# ─────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────

def _simplify_internal_display(url: str) -> str:
    """
    https://www.casinos.com/us/slots -> /us/slots
    """
    try:
        parsed = urlparse(url)
        return parsed.path or "/"
    except Exception:
        return url


def _simplify_external_display(url: str) -> str:
    """
    https://example.com/path -> example.com
    """
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _build_block_columns(
    source_url: str,
    header_left: str,
    header_right: str,
    data: Dict[str, List[str]],
    simplify_links: bool,
) -> List[List[str]]:
    """
    Returns a vertical table (list of rows) for ONE source URL.
    """
    rows: List[List[str]] = []

    # Title row (just the URL)
    rows.append([source_url, ""])
    rows.append([header_left, header_right])

    if not data:
        rows.append(["(no links found)", ""])
        return rows

    for link in sorted(data.keys()):
        anchors = [t for t in data[link] if t]
        anchor_text = " | ".join(anchors)

        if simplify_links:
            display = _simplify_internal_display(link)
            cell = f'=HYPERLINK("{link}", "{display}")'
        else:
            display = _simplify_external_display(link)
            cell = f'=HYPERLINK("{link}", "{display}")'

        rows.append([cell, anchor_text])

    return rows


# ─────────────────────────────────────────────────────────────
# Main writer
# ─────────────────────────────────────────────────────────────

def write_results(
    spreadsheet_id: str,
    internal_blocks: List[Tuple[str, Dict[str, List[str]]]],
    external_blocks: List[Tuple[str, Dict[str, List[str]]]],
) -> None:
    gc = _client_from_env()
    sh = gc.open_by_key(spreadsheet_id)

    ws_int = _ensure_worksheet(sh, "INTERNAL_LINKS")
    ws_ext = _ensure_worksheet(sh, "EXTERNAL_LINKS")

    ws_int.clear()
    ws_ext.clear()

    # ───────── INTERNAL LINKS (horizontal layout)
    col_cursor = 1  # column A
    for source_url, data in internal_blocks:
        block = _build_block_columns(
            source_url=source_url,
            header_left="INTERNAL LINK",
            header_right="ANCHOR TEXT",
            data=data,
            simplify_links=True,
        )

        ws_int.update(
            row=1,
            col=col_cursor,
            values=block,
            value_input_option="USER_ENTERED",
        )

        col_cursor += 3  # 2 cols data + 1 spacer

    # ───────── EXTERNAL LINKS (horizontal layout)
    col_cursor = 1
    for source_url, data in external_blocks:
        block = _build_block_columns(
            source_url=source_url,
            header_left="EXTERNAL LINK",
            header_right="ANCHOR TEXT",
            data=data,
            simplify_links=False,
        )

        ws_ext.update(
            row=1,
            col=col_cursor,
            values=block,
            value_input_option="USER_ENTERED",
        )

        col_cursor += 3
