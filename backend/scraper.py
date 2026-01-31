from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup


BASE = "https://www.casinos.com/"
INTERNAL_HOSTS = {"www.casinos.com", "casinos.com"}


def split_inputs(raw: str) -> List[str]:
    """
    Accepts pasted URLs from Excel / whitespace / newline / comma-separated.
    """
    raw = raw.strip()
    if not raw:
        return []
    # Replace common separators with newlines, then split
    for sep in [",", "\t", ";"]:
        raw = raw.replace(sep, "\n")
    parts = []
    for line in raw.splitlines():
        # also split on spaces within a line (Excel paste sometimes does this)
        for token in line.strip().split():
            if token.strip():
                parts.append(token.strip())
    return parts


def normalize_to_casinos(url_or_path: str) -> str:
    """
    - If full casinos.com URL: keep (normalize scheme/host minimally)
    - If relative like 'us/slots' or '/us/slots': prefix BASE
    - Otherwise: raise ValueError
    """
    s = url_or_path.strip()

    # If it's clearly a relative path
    if s.startswith("/"):
        return urljoin(BASE, s.lstrip("/"))
    if "://" not in s and s.startswith("www."):
        s = "https://" + s
    if "://" not in s:
        # treat as relative path like us/slots
        return urljoin(BASE, s.lstrip("/"))

    parsed = urlparse(s)
    host = (parsed.netloc or "").lower()
    if host in INTERNAL_HOSTS:
        # ensure https + keep path/query
        normalized = f"https://{host}{parsed.path or '/'}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized

    raise ValueError(f"Non-casinos.com URL not allowed: {s}")


def is_internal(href: str) -> bool:
    """
    Internal = casinos.com (www or apex). Relative links are internal once resolved.
    """
    parsed = urlparse(href)
    if not parsed.netloc:
        return True  # relative -> internal after resolution
    return parsed.netloc.lower() in INTERNAL_HOSTS


def extract_anchor_text(a_tag) -> str:
    """
    Prefer visible text; if empty fallback to aria-label/title.
    """
    text = a_tag.get_text(" ", strip=True)
    if text:
        return text
    for attr in ("aria-label", "title"):
        v = a_tag.get(attr)
        if v and v.strip():
            return v.strip()
    return ""


@dataclass
class PageLinks:
    source_url: str
    internal: Dict[str, List[str]]  # link -> list of anchor texts
    external: Dict[str, List[str]]


async def scrape_links(source_url: str, timeout_s: float = 20.0) -> PageLinks:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; EFCT-LinkScraper/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout_s) as client:
        r = await client.get(source_url)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    internal_map: Dict[str, set[str]] = {}
    external_map: Dict[str, set[str]] = {}

    for a in soup.select("a[href]"):
        href_raw = (a.get("href") or "").strip()
        if not href_raw:
            continue

        # Ignore page anchors, javascript, mailto, tel
        lowered = href_raw.lower()
        if lowered.startswith("#") or lowered.startswith("javascript:"):
            continue
        if lowered.startswith("mailto:") or lowered.startswith("tel:"):
            continue

        # Resolve to absolute against source_url
        abs_href = urljoin(source_url, href_raw)

        text = extract_anchor_text(a)

        if is_internal(href_raw) and urlparse(abs_href).netloc.lower() in INTERNAL_HOSTS:
            internal_map.setdefault(abs_href, set()).add(text)
        else:
            # It might be absolute casinos.com or absolute external
            if urlparse(abs_href).netloc.lower() in INTERNAL_HOSTS:
                internal_map.setdefault(abs_href, set()).add(text)
            else:
                external_map.setdefault(abs_href, set()).add(text)

    # Convert sets to sorted lists (stable output)
    internal_out = {k: sorted(v) for k, v in internal_map.items()}
    external_out = {k: sorted(v) for k, v in external_map.items()}

    return PageLinks(source_url=source_url, internal=internal_out, external=external_out)
