from __future__ import annotations

import os
import secrets
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from scraper import split_inputs, normalize_to_casinos, scrape_links
from sheets_writer import write_results


security = HTTPBasic()

def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    user = os.environ.get("APP_USER", "")
    pwd = os.environ.get("APP_PASS", "")
    if not user or not pwd:
        raise HTTPException(status_code=500, detail="Server auth not configured")

    ok_user = secrets.compare_digest(credentials.username, user)
    ok_pwd = secrets.compare_digest(credentials.password, pwd)
    if not (ok_user and ok_pwd):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


app = FastAPI(title="Casinos.com Link Scraper")


class ScrapeRequest(BaseModel):
    raw_text: Optional[str] = Field(default=None)
    urls: Optional[List[str]] = Field(default=None)

    ignore_header_footer: bool = Field(
        default=False,
        description="If true, ignore links found inside <header>, <footer>, and <nav>.",
    )


def gather_inputs(req: ScrapeRequest) -> List[str]:
    if req.urls:
        return [u.strip() for u in req.urls if u and u.strip()]
    if req.raw_text and req.raw_text.strip():
        return split_inputs(req.raw_text)
    return []


@app.post("/scrape", dependencies=[Depends(require_auth)])
async def scrape(req: ScrapeRequest) -> Dict[str, Any]:
    urls_in = gather_inputs(req)

    if not (1 <= len(urls_in) <= 150):
        raise HTTPException(status_code=400, detail="Provide between 1 and 150 URLs/paths.")

    urls_in = list(dict.fromkeys(urls_in))

    normalized: List[str] = []
    errors: List[str] = []

    for u in urls_in:
        try:
            normalized.append(normalize_to_casinos(u))
        except Exception as e:
            errors.append(f"{u} -> {e}")

    if not normalized:
        raise HTTPException(status_code=400, detail={"message": "No valid casinos.com URLs/paths.", "errors": errors})

    internal_blocks = []
    external_blocks = []

    for u in normalized:
        try:
            page = await scrape_links(u, ignore_header_footer=req.ignore_header_footer)
            internal_blocks.append((page.source_url, page.internal))
            external_blocks.append((page.source_url, page.external))
        except Exception as e:
            internal_blocks.append((u, {}))
            external_blocks.append((u, {}))
            errors.append(f"Failed to scrape {u}: {e}")

    spreadsheet_id = os.environ.get("GSHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise HTTPException(status_code=500, detail="Missing env var GSHEETS_SPREADSHEET_ID")

    try:
        write_results(spreadsheet_id, internal_blocks, external_blocks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write to Google Sheets: {e}")

    return {
        "ok": True,
        "input_count": len(urls_in),
        "normalized_count": len(normalized),
        "errors": errors,
    }


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def home():
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Links Input</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">

    <style>
      :root{
        --bg: #f6f7fb;
        --card: #ffffff;
        --text: #0f1222;
        --muted: #6b7280;
        --shadow: 0 18px 60px rgba(15, 18, 34, 0.12);
        --shadow-soft: 0 10px 30px rgba(15, 18, 34, 0.10);
        --radius: 18px;
        --grad: linear-gradient(90deg, #ff2aa6 0%, #ff2aa6 40%, #b400ff 100%);
      }

      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        background: radial-gradient(1200px 800px at 50% 0%, #ffffff 0%, var(--bg) 55%, #eef0f7 100%);
        color: var(--text);
        display: grid;
        place-items: center;
        padding: 28px 16px;
      }

      .wrap {
        width: 100%;
        max-width: 820px;
        display: grid;
        gap: 14px;
        place-items: center;
      }

      h1 {
        margin: 0 0 6px 0;
        font-size: 42px;
        font-weight: 800;
        letter-spacing: -0.02em;
        background: var(--grad);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
      }

      .sub {
        margin: 0 0 18px 0;
        color: var(--muted);
        font-size: 14px;
        text-align: center;
        max-width: 560px;
        line-height: 1.45;
      }

      .card {
        width: 100%;
        background: var(--card);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        padding: 18px;
      }

      textarea {
        width: 100%;
        min-height: 240px;
        resize: vertical;
        border: none;
        outline: none;
        border-radius: 14px;
        padding: 16px 16px;
        background: #ffffff;
        box-shadow: var(--shadow-soft);
        color: var(--text);
        font-size: 14px;
        line-height: 1.45;
      }

      .row {
        margin-top: 14px;
        display: grid;
        gap: 10px;
        place-items: center;
      }

      .toggle {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 13px;
        color: var(--muted);
        user-select: none;
      }

      .toggle input {
        width: 18px;
        height: 18px;
        accent-color: #ff2aa6;
      }

      .btn {
        border: none;
        cursor: pointer;
        border-radius: 999px;
        padding: 12px 28px;
        font-weight: 800;
        color: #fff;
        background: var(--grad);
        box-shadow: 0 14px 28px rgba(180, 0, 255, 0.18), 0 10px 20px rgba(255, 42, 166, 0.20);
        transition: transform 0.08s ease, filter 0.15s ease, opacity 0.15s ease;
        user-select: none;
      }

      .btn:hover { filter: brightness(1.03); }
      .btn:active { transform: translateY(1px); }
      .btn:disabled { opacity: 0.55; cursor: not-allowed; }

      .status {
        margin-top: 14px;
        border-radius: 14px;
        padding: 12px 14px;
        background: #0b0f1a;
        color: #e5e7eb;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 12px;
        white-space: pre-wrap;
        display: none;
      }
    </style>
  </head>

  <body>
    <div class="wrap">
      <h1>Links Input</h1>
      <p class="sub">
        Paste your URL(s) in this box, then click on "Generate" to update the Google Spreadsheet
      </p>

      <div class="card">
        <textarea id="raw" placeholder="Paste here, one per line:
us/slots
us/poker
us/blackjack"></textarea>

        <div class="row">
          <label class="toggle">
            <input id="ignoreHF" type="checkbox" />
            Ignore links in headers/footers/nav
          </label>

          <button id="run" class="btn">Generate</button>
        </div>

        <pre id="out" class="status"></pre>
      </div>
    </div>

    <script>
      const btn = document.getElementById("run");
      const out = document.getElementById("out");
      const ta  = document.getElementById("raw");
      const ignoreHF = document.getElementById("ignoreHF");

      function countLines(text) {
        return text.split(/\\r?\\n/).map(l => l.trim()).filter(Boolean).length;
      }

      function setStatus(text, show=true) {
        out.textContent = text;
        out.style.display = show ? "block" : "none";
      }

      function setButtonLoading(isLoading) {
        btn.disabled = isLoading;
        btn.textContent = isLoading ? "Generating..." : "Generate";
      }

      btn.addEventListener("click", async () => {
        const n = countLines(ta.value);
        if (n < 1) return setStatus("Please paste at least 1 URL/path.", true);
        if (n > 150) return setStatus("Too many lines. Max is 150.", true);

        setButtonLoading(true);
        setStatus("Running... This may take a moment.", true);

        try {
          const res = await fetch("/scrape", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              raw_text: ta.value,
              ignore_header_footer: ignoreHF.checked
            })
          });

          const data = await res.json();

          if (!res.ok) {
            setStatus("ERROR\\n" + JSON.stringify(data, null, 2), true);
          } else {
            const errs = (data.errors && data.errors.length)
              ? ("\\n\\nWarnings:\\n- " + data.errors.join("\\n- "))
              : "";
            setStatus(
              "Done ✅\\n" +
              `Input count: ${data.input_count}\\n` +
              `Normalized: ${data.normalized_count}` +
              errs +
              "\\n\\nCheck your Google Sheet tabs: INTERNAL_LINKS and EXTERNAL_LINKS.",
              true
            );
          }
        } catch (e) {
          setStatus("ERROR\\n" + e.toString(), true);
        } finally {
          setButtonLoading(false);
        }
      });
    </script>
  </body>
</html>
"""
