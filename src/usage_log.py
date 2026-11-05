"""Detailed usage log for the hosted app: one row per event in data/logs/usage.csv (opens in Excel).

Logged per event: UTC time, event type (answered, blocked, error), approximate country, an anonymous
visitor id (salted hash of the IP address; the address itself is never stored), the question and the
answer, retrieved and cited documents, model, tokens, estimated cost, response time and quotation
problems. The visitor's country comes from a CDN header if present (Cloudflare "CF-IPCountry") or
from a local MaxMind GeoLite2 Country database (path in CSCLBOT_GEOIP_DB or data/GeoLite2-Country.mmdb);
otherwise it is "unknown". Requests from this machine are "local".

The log folder can be moved with CSCLBOT_LOG_DIR (in the cloud, point it at a mounted volume).
"""
from __future__ import annotations

import csv
import hashlib
import ipaddress
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.environ.get("CSCLBOT_LOG_DIR", ROOT / "data" / "logs"))
LOG_FILE = LOG_DIR / "usage.csv"
GEOIP_DB = Path(os.environ.get("CSCLBOT_GEOIP_DB", ROOT / "data" / "GeoLite2-Country.mmdb"))
COLUMNS = [
    "timestamp_utc", "event", "country", "visitor", "question", "answer", "retrieved_docs", "cited_docs",
    "n_passages", "model", "input_tokens", "output_tokens", "est_cost_usd", "seconds", "quote_problems", "note",
]
_lock = threading.Lock()
_reader = None


def _salt() -> str:
    """Secret for the visitor hash: CSCLBOT_HASH_SALT, else a random value kept next to the log."""
    if os.environ.get("CSCLBOT_HASH_SALT"):
        return os.environ["CSCLBOT_HASH_SALT"]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    f = LOG_DIR / ".salt"
    if not f.exists():
        f.write_text(secrets.token_hex(16))
    return f.read_text().strip()


def visitor_id(ip: str) -> str:
    return hashlib.sha256((_salt() + ip).encode()).hexdigest()[:12]


def country_for(ip: str, headers: dict | None = None) -> str:
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    for name in ("cf-ipcountry", "x-country-code"):
        code = headers.get(name, "").strip().upper()
        if len(code) == 2 and code.isalpha() and code != "XX":
            return code
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    if addr.is_loopback or addr.is_private:
        return "local"
    global _reader
    if _reader is None and GEOIP_DB.exists():
        import maxminddb

        _reader = maxminddb.open_database(str(GEOIP_DB))
    if _reader is None:
        return "unknown"
    rec = _reader.get(ip) or {}
    return (rec.get("country") or rec.get("registered_country") or {}).get("iso_code", "unknown")


def log_event(**fields) -> None:
    """Append one row; unknown fields are ignored, missing ones left blank."""
    row = {c: fields.get(c, "") for c in COLUMNS}
    row["timestamp_utc"] = row["timestamp_utc"] or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for key in ("retrieved_docs", "cited_docs", "quote_problems"):
        if isinstance(row[key], (list, tuple)):
            row[key] = "; ".join(map(str, row[key]))
    with _lock:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        new = not LOG_FILE.exists()
        # utf-8-sig so Excel reads accented characters correctly
        with LOG_FILE.open("a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if new:
                writer.writeheader()
            writer.writerow(row)
