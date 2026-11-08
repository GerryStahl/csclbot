"""Build data/references.json and reports/references.csv.

Merges, read-only:
  data/inputs/ijcscl.json                     ijCSCL article records (titles/authors hand-corrected)
  data/raw/crossref_ijcscl.json               Crossref metadata (pages, issue, full author lists)
  ../elibrary/cache/elibrary_cache.json       22 books / 337 chapters + original-publication references
  data/raw/elibrary_chapter_pages.json        chapter page ranges in the e-library PDFs

Run src/fetch_crossref.py and src/locate_chapter_pages.py first. Output schema:
documentation/references_schema.md.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

from apa import (
    JOURNAL_IJCSCL,
    author,
    authors_from_ampersand_string,
    cite_short,
    clean_text,
    en_dash,
    format_reference,
    norm_key,
    parse_authors,
    parse_reference,
    plain,
    sentence_case_if_shouting,
)
from fetch_crossref import doi_for

ROOT = Path(__file__).resolve().parent.parent
IJCSCL_JSON = ROOT / "data" / "inputs" / "ijcscl.json"
ELIB_JSON = ROOT.parent / "elibrary" / "cache" / "elibrary_cache.json"
CROSSREF = ROOT / "data" / "raw" / "crossref_ijcscl.json"
CHAPTER_PAGES = ROOT / "data" / "raw" / "elibrary_chapter_pages.json"
OUT_JSON = ROOT / "data" / "references.json"
OUT_CSV = ROOT / "reports" / "references.csv"

STAHL = author("Stahl", "Gerry")
ELIBRARY_URL = "https://gerrystahl.net/elibrary/"
# Chapters in the e-library volumes are cited "In G. Stahl (Ed.), <book>"; set a list of other
# editors (or an empty list to cite the chapter as part of an authored book) here per book number.
BOOK_EDITORS: dict[int, list[dict]] = {}
SUBTYPES = {"editorial": "editorial", "book review": "book_review", "corrected": "correction"}


# ------------------------------------------------------------------ ijCSCL articles
# Page ranges missing in Crossref, read from the PDF running head (page counts agree with the PDFs)
PAGE_OVERRIDES = {"10.1007/s11412-014-9205-8": "117\u2013138", "10.1007/s11412-014-9206-7": "161\u2013181"}
# Crossref records that split a name wrongly: (family, given) as delivered -> corrected
NAME_FIXES = {("Perit Çakır", "Murat"): ("Çakır", "Murat Perit"), ("Ulrich Hoppe", "H."): ("Hoppe", "H. Ulrich")}


def crossref_authors(item: dict) -> list[dict]:
    """Personal authors only: Crossref sometimes lists an affiliation as an organisational 'author'."""
    out = []
    for a in item.get("author", []):
        if a.get("family"):
            family, given = NAME_FIXES.get((a["family"], a.get("given", "")), (a["family"], a.get("given", "")))
            out.append(author(clean_text(family), clean_text(given)))
    return out


def open_license(item: dict | None) -> dict | None:
    """Creative Commons licence deposited by the publisher in Crossref, e.g. {'name': 'CC BY 4.0', 'url': ...}."""
    for lic in (item or {}).get("license", []) or []:
        m = re.search(r"creativecommons\.org/licenses/([a-z-]+)/([\d.]+)", lic.get("URL", ""))
        if m:
            return {"name": f"CC {m.group(1).upper()} {m.group(2)}", "url": f"https://creativecommons.org/licenses/{m.group(1)}/{m.group(2)}/", "source": "Crossref"}
    return None


def build_ijcscl(articles: dict, crossref: dict) -> list[dict]:
    by_title = {norm_key(v["title"][0]): v for v in crossref.values() if v.get("title")}
    docs, seen_doi = [], {}
    for rec_id, rec in articles.items():
        issues: list[str] = []
        doi = doi_for(rec)
        cr = crossref.get(doi) if doi else by_title.get(norm_key(rec["title"]))
        if cr and not doi:
            doi = cr["DOI"]
        prov = {"authors": "ijcscl.json", "title": "ijcscl.json", "pages": None, "issue": "ijcscl.json"}
        subtype = SUBTYPES.get(rec.get("editorial") or "")
        title = clean_text(rec["title"])
        if re.match(r"^(correction|erratum)\b", title, re.I):
            subtype = "correction"

        authors = authors_from_ampersand_string(rec["authors"])
        if cr and crossref_authors(cr):
            authors, prov["authors"] = crossref_authors(cr), "crossref"
        else:
            issues.append("authors_from_ijcscl_json_only (may be truncated)")

        if cr and cr.get("title"):
            cr_title = clean_text(cr["title"][0])
            if norm_key(cr_title) != norm_key(title):
                defective = norm_key(cr_title).startswith(norm_key(title)) or norm_key(title) == norm_key(rec["authors"] or "") or " & " in title
                if defective:
                    title, prov["title"] = cr_title, "crossref"
                    issues.append("title_from_crossref (ijcscl.json title truncated or not a title)")
                else:
                    issues.append(f"title differs from Crossref, ijcscl.json kept (Crossref: {cr_title})")
        volume, issue = str(rec["volume"]), str(rec["issue"])
        if cr and cr.get("volume"):
            volume, issue, prov["issue"] = str(cr["volume"]), str(cr.get("issue") or issue), "crossref"
            if volume != str(rec["volume"]) or not issue.startswith(str(rec["issue"])):
                issues.append(f"volume/issue differs from ijcscl.json ({rec['volume']}({rec['issue']}))")
        issue = en_dash(issue)
        year = int(rec["year"])
        if year != 2005 + int(volume):
            issues.append(f"year {year} does not match volume {volume} (expected {2005 + int(volume)})")

        pages = article_number = None
        if doi in PAGE_OVERRIDES:
            pages, prov["pages"] = PAGE_OVERRIDES[doi], "PDF running head"
        elif cr and cr.get("page"):
            pages, prov["pages"] = en_dash(cr["page"]), "crossref"
        elif cr and cr.get("article-number"):
            article_number, prov["pages"] = cr["article-number"], "crossref"
        else:
            issues.append("no_page_range (Crossref has none)")
        if doi and doi in seen_doi:
            issues.append(f"duplicate DOI shared with {seen_doi[doi]}")
        seen_doi.setdefault(doi, rec_id)

        kind = subtype or "journal_article"
        d = {
            "type": kind,
            "subtype": subtype,
            "authors": authors,
            "year": year,
            "title": title,
            "journal": JOURNAL_IJCSCL,
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "article_number": article_number,
            "doi": doi,
        }
        docs.append(
            {
                "id": f"ijcscl:{rec_id}",
                "type": kind,
                "in_corpus": True,
                "authors": authors,
                "year": year,
                "title": title,
                "container": {"title": JOURNAL_IJCSCL, "volume": volume, "issue": issue},
                "pages": page_obj(pages, prov["pages"]) if pages else None,
                "article_number": article_number,
                "doi": doi,
                "url": None,
                "apa_md": format_reference(d),
                "corpus": {
                    "project": "anniversary",
                    "record_id": rec_id,
                    "volume": rec["volume"],
                    "issue": rec["issue"],
                    "article_number": rec["article_number"],
                },
                "related": [],
                "license": open_license(cr),
                "provenance": prov,
                "_sort": (int(volume), int(re.match(r"\d+", issue).group()), rec["article_number"] or 0, rec_id),
                "issues": issues,
            }
        )
    return docs


def page_obj(display: str | None, basis: str, **extra) -> dict | None:
    if not display:
        return None
    first, _, last = display.partition("\u2013")
    return {"first": first, "last": last or first, "display": display, "basis": basis, **extra}


# ------------------------------------------------------------------ e-library books and chapters
def book_meta(book: dict, n_pdf_pages: int | None, front: dict) -> dict:
    """Citations target the e-library edition actually indexed (latest copyright year, Lulu);
    the publisher/year Gerry recorded (e.g. MIT Press 2006) are kept as original_publication."""
    ref = clean_text(book["book_reference"])
    recorded_year = int(re.search(r"\((\d{4})\)", ref).group(1))
    years = front.get("copyright_years") or [recorded_year]
    urls = re.findall(r"https?://\S+", ref)
    no_url = re.sub(r"\s*https?://\S+", "", ref).strip(" .")
    publisher = re.sub(r"\.\s*$", "", no_url.rsplit(":", 1)[-1]).strip() if ":" in no_url else None
    slug = book["book_name"].split(".")[1]
    doi = next((re.sub(r"^https?://(?:dx\.)?doi\.org/(?:https?://(?:dx\.)?doi\.org/)?", "", u) for u in urls if "doi.org" in u), None)
    return {
        "id": f"elibrary:{book['book_number']}",
        "number": book["book_number"],
        "title": clean_text(book["book_title"]),
        "authors": [STAHL],
        "editors": BOOK_EDITORS.get(book["book_number"], [STAHL]),
        "year": max(years),
        "copyright_years": years,
        "publisher": re.sub(r"\.com$", "", front.get("published_by") or "Gerry Stahl at Lulu"),
        "url": f"{ELIBRARY_URL}{slug}",
        "url_basis": "derived from PDF file name; verify",
        "pdf": book["book_name"],
        "pdf_pages": n_pdf_pages,
        "original_publication": {
            "year": recorded_year,
            "publisher": publisher,
            "doi": doi if doi and doi.startswith("10.") else None,
            "reference_as_recorded": ref,
        },
    }


def clean_chapter_title(title: str) -> str:
    t = clean_text(title)
    t = re.sub(r"^\d+\(\d+(?:&\d+)?\):\s*", "", t)
    t = re.sub(r"^chapter\s+(?:\d+|[ivx]+)\s*[.:]\s*", "", t, flags=re.I)
    t = sentence_case_if_shouting(t)
    return re.sub(r"(:\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t) if t.isupper() or t != clean_text(title) else t


def chapter_authors(ch: dict, parsed: dict | None) -> list[dict]:
    if parsed and parsed.get("parse_ok") and parsed.get("authors"):
        return parsed["authors"]
    text = clean_text(ch["chapter_author"])
    # "Stahl, G., & Hesse, F." is APA order; "G. Stahl, T. Koschmann & D. Suthers" is initials first
    return parse_authors(text) if re.match(r"^[^,.]{2,},\s*[A-ZÇ]\.", text) else authors_from_ampersand_string(text)


def find_ijcscl_match(parsed: dict | None, chapter_title: str, raw_title: str, book_number: int, index: dict) -> dict | None:
    """ijCSCL document that this chapter reprints (by title; book 16 also by vol(issue) prefix)."""
    keys = [norm_key(chapter_title)]
    if parsed and parsed.get("title"):
        keys.insert(0, norm_key(parsed["title"]))
    for key in keys:
        for doc in index["title"].get(key, []):
            return doc
    if book_number == 16:
        m = re.match(r"^(\d+)\((\d+)(?:&\d+)?\):", clean_text(raw_title))
        if m:
            cands = [d for d in index["issue"].get((m.group(1), m.group(2)), []) if d["type"] == "editorial"]
            if len(cands) == 1:
                return cands[0]
    return None


def build_elibrary(cache: dict, pages: dict, ijcscl_docs: list[dict]) -> tuple[list[dict], list[dict]]:
    index = {"title": {}, "issue": {}}
    for d in ijcscl_docs:
        index["title"].setdefault(norm_key(d["title"]), []).append(d)
        index["issue"].setdefault((d["container"]["volume"], re.match(r"\d+", d["container"]["issue"]).group()), []).append(d)

    books, docs = [], []
    for book in cache["books"]:
        bn = book["book_number"]
        pdf_pages = next((v["pdf_pages"] for k, v in pages.items() if k.startswith(f"{bn}.")), None)
        meta = book_meta(book, pdf_pages, pages["_books"][str(bn)])
        books.append(meta)
        for ch in book["book_chapters"]:
            cn = ch["chapter_number"]
            issues: list[str] = []
            raw_ref = ch["chapter_reference"].strip()
            parsed = parse_reference(raw_ref) if raw_ref else None
            title = clean_chapter_title(ch["chapter_title"])
            match = find_ijcscl_match(parsed, title, ch["chapter_title"], bn, index)
            if match:
                authors = match["authors"]
            else:
                authors = chapter_authors(ch, parsed)
            original_year = (match or {}).get("year") or (parsed or {}).get("year")
            if original_year and original_year > meta["year"]:
                issues.append(f"original year {original_year} is later than the e-library edition year {meta['year']}")

            loc = pages[f"{bn}.{cn}"]
            display = None
            if loc["first"]:
                display = str(loc["first"]) if loc["last"] in (None, loc["first"]) else f"{loc['first']}\u2013{loc['last']}"
            if loc["method"] != "matched":
                issues.append("start_page_estimated (chapter start not found in PDF text)")
            if loc["last_estimated"]:
                issues.append("end_page_estimated (from page count; chapter not followed by a matched chapter)")

            d = {
                "type": "book_chapter",
                "authors": authors,
                "year": meta["year"],
                "title": title,
                "editors": meta["editors"],
                "book_title": meta["title"],
                "pages": display,
                "publisher": meta["publisher"],
                "url": meta["url"],
                "original_year": str(original_year) if original_year else None,
            }
            doc_id = f"elibrary:{bn}.{cn}"
            doc = {
                "id": doc_id,
                "type": "book_chapter",
                "in_corpus": True,
                "authors": authors,
                "year": meta["year"],
                "original_year": original_year,
                "title": title,
                "container": {
                    "title": meta["title"],
                    "editors": meta["editors"],
                    "publisher": meta["publisher"],
                    "book_id": meta["id"],
                },
                "pages": page_obj(display, "elibrary_pdf", method=loc["method"], chunk_page_offset=(loc["first"] - 1) if loc["first"] else None),
                "doi": None,
                "url": meta["url"],
                "apa_md": format_reference(d),
                "corpus": {"project": "elibrary", "book_number": bn, "chapter_number": cn, "chapter_title_as_recorded": clean_text(ch["chapter_title"])},
                "related": [],
                "provenance": {
                    "authors": "ijCSCL/Crossref" if match else ("chapter_reference" if parsed and parsed["parse_ok"] else "elibrary chapter_author"),
                    "title": "elibrary chapter_title",
                    "pages": "PDF scan (printed page = PDF page index + 1)",
                },
                "_sort": (bn, cn, 0),
                "issues": issues,
            }
            docs.append(doc)

            if match:
                doc["related"].append({"relation": "reprint_of", "id": match["id"]})
                match["related"].append({"relation": "reprinted_in", "id": doc_id})
                if parsed and parsed.get("parse_ok"):
                    fam = lambda people: {norm_key(a.get("family", "")) for a in people}
                    if fam(parsed["authors"]) != fam(match["authors"]):
                        doc["issues"].append("chapter_reference authors differ from the matched article's (recorded reference may be a different version)")
                if parsed and parsed.get("doi") and match.get("doi") and parsed["doi"].lower() != match["doi"].lower():
                    doc["issues"].append(f"chapter_reference DOI {parsed['doi']} differs from the matched article's DOI {match['doi']}")
                continue
            if not parsed:
                continue
            if parsed.get("parse_ok") is False:
                docs.append(original_item(doc_id, parsed, bn, cn, raw_only=True))
                doc["related"].append({"relation": "originally_published_as", "id": f"{doc_id}#original"})
                continue
            if is_same_book_self_publication(parsed, meta):
                continue
            if parsed["type"] == "journal_article" and "Computer-Supported Collaborative Learning" in parsed.get("journal", ""):
                doc["issues"].append("ijCSCL reference in chapter_reference but no matching article record in ijcscl.json")
            docs.append(original_item(doc_id, parsed, bn, cn))
            doc["related"].append({"relation": "originally_published_as", "id": f"{doc_id}#original"})
    link_repeated_chapters(docs)
    return books, docs


def link_repeated_chapters(docs: list[dict]) -> None:
    """Chapters with the same title that appear in more than one e-library volume."""
    groups: dict[str, list[dict]] = {}
    for d in docs:
        if d["id"].startswith("elibrary:") and not d["id"].endswith("#original"):
            groups.setdefault(norm_key(d["title"]), []).append(d)
    for key, members in groups.items():
        if len(key) >= 25 and len({m["corpus"]["book_number"] for m in members}) > 1:
            for m in members:
                m["related"] += [{"relation": "same_text_as", "id": o["id"]} for o in members if o is not m]


def is_same_book_self_publication(parsed: dict, meta: dict) -> bool:
    """Reference that merely points at the same e-library volume (e.g. 'In G. Stahl (Ed.), Marx and Heidegger')."""
    return parsed["type"] == "book_chapter" and norm_key(parsed.get("book_title", "")) == norm_key(meta["title"]) and "Lulu" in (parsed.get("publisher") or "")


def original_item(chapter_id: str, parsed: dict, bn: int, cn: int, raw_only: bool = False) -> dict:
    """Original publication of a chapter (not itself in the corpus), cited from Gerry's own APA string."""
    issues = []
    if raw_only:
        text = re.sub(r",\s*Article\s+\d+", "", clean_text(parsed["raw"]))
        issues.append("reference_not_parsed (cleaned original text used)")
        return {
            "id": f"{chapter_id}#original",
            "type": "other",
            "in_corpus": False,
            "authors": parsed.get("authors", []),
            "year": parsed.get("year"),
            "title": None,
            "container": {},
            "pages": None,
            "doi": None,
            "url": None,
            "apa_md": text,
            "corpus": {"project": "elibrary", "book_number": bn, "chapter_number": cn},
            "related": [{"relation": "original_of", "id": chapter_id}],
            "provenance": {"all": "elibrary chapter_reference (verbatim, cleaned)"},
            "_sort": (bn, cn, 1),
            "issues": issues,
        }
    ptype = parsed["type"]
    d = dict(parsed)
    if ptype == "journal_article" and not (parsed.get("pages") or parsed.get("volume")):
        issues.append("no_volume_or_pages")
    year = parsed["year"]
    container = {
        k: parsed.get(k)
        for k in ("journal", "volume", "issue", "editors_text", "book_title", "publisher", "venue", "location")
        if parsed.get(k)
    }
    return {
        "id": f"{chapter_id}#original",
        "type": ptype,
        "in_corpus": False,
        "authors": parsed["authors"],
        "year": year,
        "title": parsed["title"],
        "container": container,
        "pages": page_obj(parsed.get("pages"), "chapter_reference") if parsed.get("pages") else None,
        "doi": parsed.get("doi"),
        "url": parsed.get("url"),
        "apa_md": format_reference(d),
        "corpus": {"project": "elibrary", "book_number": bn, "chapter_number": cn},
        "related": [{"relation": "original_of", "id": chapter_id}],
        "provenance": {"all": "parsed from elibrary chapter_reference"},
        "_sort": (bn, cn, 1),
        "issues": issues,
    }


# ------------------------------------------------------------------ output
GROUPS = [("ijcscl:", "ijCSCL article"), ("elibrary:", "e-library chapter")]


def finish(doc: dict) -> dict:
    doc["apa"] = plain(doc["apa_md"])
    doc["cite_short"] = cite_short(doc["authors"], doc["year"])
    issues = doc.pop("issues")
    doc["review"] = {"status": "review" if issues else "ok", "issues": issues}
    return doc


def group_of(doc: dict) -> str:
    if doc["id"].startswith("ijcscl:"):
        return "ijCSCL article"
    return "original publication (not in corpus)" if doc["id"].endswith("#original") else "e-library chapter"


def write_csv(docs: list[dict]) -> None:
    OUT_CSV.parent.mkdir(exist_ok=True)
    order = {"ijCSCL article": 0, "e-library chapter": 1, "original publication (not in corpus)": 2}
    rows = sorted(docs, key=lambda d: (order[group_of(d)], d["_sort"]) if group_of(d) != "original publication (not in corpus)" else (2, d["_sort"]))
    cols = ["id", "group", "type", "in_corpus", "year", "apa_reference", "pages", "doi", "related_ids", "status", "issues"]
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for d in rows:
            w.writerow(
                [
                    d["id"],
                    group_of(d),
                    d["type"],
                    d["in_corpus"],
                    d["year"],
                    d["apa"],
                    d["pages"]["display"] if d.get("pages") else "",
                    d.get("doi") or "",
                    "; ".join(f"{r['relation']}:{r['id']}" for r in d["related"]),
                    d["review"]["status"],
                    " | ".join(d["review"]["issues"]),
                ]
            )


def main() -> None:
    articles = json.loads(IJCSCL_JSON.read_text(encoding="utf-8"))
    crossref = json.loads(CROSSREF.read_text(encoding="utf-8"))
    cache = json.loads(ELIB_JSON.read_text(encoding="utf-8"))
    pages = json.loads(CHAPTER_PAGES.read_text(encoding="utf-8"))

    ijcscl_docs = build_ijcscl(articles, crossref)
    books, elib_docs = build_elibrary(cache, pages, ijcscl_docs)
    docs = sorted(ijcscl_docs + elib_docs, key=lambda d: (group_of(d) != "ijCSCL article", d["_sort"]))
    for d in docs:
        finish(d)
    write_csv(docs)
    for d in docs:
        d.pop("_sort")

    OUT_JSON.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated": date.today().isoformat(),
                "style": "APA 7",
                "notes": "See documentation/references_schema.md. 'apa' is plain text, 'apa_md' marks italics with *asterisks*.",
                "books": books,
                "documents": docs,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    by_group: dict[str, list[int]] = {}
    for d in docs:
        stats = by_group.setdefault(group_of(d), [0, 0])
        stats[0] += 1
        stats[1] += d["review"]["status"] == "review"
    for g, (n, r) in by_group.items():
        print(f"{g}: {n} documents, {r} flagged for review")


if __name__ == "__main__":
    main()
