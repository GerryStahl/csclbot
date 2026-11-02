"""Fetch Crossref metadata (pages, volume, issue, authors, title) for every ijCSCL article.

Reads data/inputs/ijcscl.json (copy of ../anniversary/data/processed/ijcscl.json), resolves each article's DOI
(from the record, or from the 2016+ file-name id), and caches the Crossref response in
data/raw/crossref_ijcscl.json (git-ignored; re-runnable, only missing DOIs are fetched).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
IJCSCL_JSON = ROOT / "data" / "inputs" / "ijcscl.json"
CACHE = ROOT / "data" / "raw" / "crossref_ijcscl.json"
API = "https://api.crossref.org/works/"
HEADERS = {"User-Agent": "csclbot/0.1 (mailto:gerry@gerrystahl.net)"}
ID_DOI = re.compile(r"_(10\.\d{4,9})_(s11412-[0-9a-z-]+?)_")


def doi_for(article: dict) -> str | None:
    """DOI from the record, else derived from the 2016+ id (slash encoded as underscore)."""
    if (article.get("doi") or "").strip().startswith("10."):
        return article["doi"].strip()
    m = ID_DOI.search(article["id"] + "_")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def search_doi(article: dict) -> dict | None:
    """Title search restricted to the journal's ISSNs, for the few records lacking a usable DOI."""
    params = {
        "query.bibliographic": article["title"],
        "filter": "issn:1556-1607,issn:1556-1615",
        "rows": 3,
    }
    items = requests.get("https://api.crossref.org/works", params=params, headers=HEADERS, timeout=30)
    for item in items.json()["message"]["items"]:
        if norm(item["title"][0]) == norm(article["title"]):
            return item
    return None


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def main() -> None:
    articles = json.loads(IJCSCL_JSON.read_text(encoding="utf-8"))
    cache: dict = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    todo = sorted({d for a in articles.values() if (d := doi_for(a)) and d not in cache})
    print(f"{len(cache)} cached, {len(todo)} to fetch")
    for i, doi in enumerate(todo, 1):
        try:
            r = requests.get(API + doi, headers=HEADERS, timeout=30)
            cache[doi] = r.json()["message"] if r.status_code == 200 else {"_error": r.status_code}
        except Exception as exc:  # network hiccup: record and continue
            cache[doi] = {"_error": str(exc)}
        if i % 25 == 0:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  {i}/{len(todo)}")
        time.sleep(0.2)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    for a in articles.values():
        if doi_for(a) is None:
            item = search_doi(a)
            print(f"title search {a['id']}: {item['DOI'] if item else 'NOT FOUND'}")
            if item:
                cache[item["DOI"]] = item
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    errs = [d for d, v in cache.items() if "_error" in v]
    print(f"done; {len(errs)} errors: {errs[:10]}")


if __name__ == "__main__":
    main()
