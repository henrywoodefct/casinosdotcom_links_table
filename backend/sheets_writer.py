from __future__ import annotations

from typing import Dict, List, Tuple
import json
import os
import tempfile
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials


def _service_account_path_from_env() -> str:
    """
    Supports two modes:
    1) GSHEETS_KEY_JSON: full service account JSON pasted into an env var (best for Render)
    2) GSHEETS_KEY_PATH: path to a local JSON file (your current local setup)
    """
    key_json = os.environ.get("GSHEETS_KEY_JSON")
    if key_json and key_json.strip():
        data = json.loads(key_json)
        fd, path = tempfile.mkstemp(prefix="gsheets_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    key_path = os.environ.get("GSHEETS_KEY_PATH")
    if key_path and Path(key_path).exists():
        return key_path

    raise RuntimeError("Missing Google Sheets credentials. Set GSHEETS_KEY_JSON (preferred) or GSHEETS_KEY_PATH.")


def _client_from_env() -> gspread.Client:
    key_path = _service_account_path_from_env()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(key_path, scopes=scopes)
    return gspread.authorize(creds)


def _ensure_worksheet(sh, title: str) -> gspread.Worksheet:
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=10)


def _block_rows(source_url: str, header_left: str, header_right: str, data: Dict[str, List[str]]) -> List[List[str]]:
    """
    data: link -> [anchor texts]
    We aggregate anchors into one cell joined by " | "
    """
    rows: List[List[str]] = []
    rows.append([f"SOURCE URL: {source_url}", ""])
    rows.append([header_left, header_right])

    if not data:
        rows.append(["(no links found)", ""])
        rows.append(["", ""])
        return rows

    for link in sorted(data.keys()):
        anchors = [t for t in data[link] if t is not None]
        anchors_joined = " | ".join([a for a in anchors if a != ""])
        rows.append([link, anchors_joined])

    rows.append(["", ""])  # blank line between blocks
    return rows


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

    int_rows: List[List[str]] = []
    for source_url, data in internal_blocks:
        int_rows.extend(_block_rows(source_url, "INTERNAL LINK", "INT. ANCHOR TEXT", data))

    ext_rows: List[List[str]] = []
    for source_url, data in external_blocks:
        ext_rows.extend(_block_rows(source_url, "EXTERNAL LINK", "EXT. ANCHOR TEXT", data))

    if int_rows:
        ws_int.update("A1", int_rows, value_input_option="RAW")
    if ext_rows:
        ws_ext.update("A1", ext_rows, value_input_option="RAW")
