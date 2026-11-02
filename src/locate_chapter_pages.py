"""Locate each e-library chapter's first/last page in its book PDF.

Reads ../elibrary/cache/elibrary_cache.json and ../elibrary/sourcepdfs/*.pdf (both read-only).
PDF page index + 1 equals the printed page number in these books. A chapter's first page is
found by matching the start of its text against page text; chapters that cannot be matched
(e.g. part dividers) are placed from the previous chapter's start plus its page count and
marked "estimated". Also records each volume's copyright years and publisher. Output: data/raw/elibrary_chapter_pages.json (git-ignored).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
ELIB = ROOT.parent / "elibrary"
OUT = ROOT / "data" / "raw" / "elibrary_chapter_pages.json"


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text.lower()))


def candidates(chapter: dict, pages: list[str]) -> list[int]:
    """1-based pages whose text contains the start of the chapter text."""
    key = norm(chapter["chapter_text"])[:60]
    found = [i + 1 for i, p in enumerate(pages) if key and key in p]
    if not found:
        # part-divider pages carry their own page number inside the text ("Part II ... 104 ...")
        m = re.match(r"Part [IVX]+\b\D{0,60}?(\d{1,3})\b", chapter["chapter_text"][:120])
        if m and 0 < int(m.group(1)) <= len(pages):
            found = [int(m.group(1))]
    return found


def is_blank(page_text: str, header_len: int) -> bool:
    """Page with nothing but the running header and page number."""
    return len(re.sub(r"\d", "", page_text)) <= header_len + 5


def starts_at_top(chapter: dict, page_text: str, header_len: int) -> bool:
    """True when the chapter text begins right after the running header of its first page."""
    key = norm(chapter["chapter_text"])[:60]
    return page_text.find(key) <= header_len + 8


def choose_starts(chapters: list[dict], cands: list[list[int]]) -> list[tuple[int | None, str]]:
    starts: list[tuple[int | None, str]] = []
    for k, ch in enumerate(chapters):
        n = ch["chapter_number_of_pages"] or 1
        if k == 0:
            nxt = cands[1] if len(cands) > 1 else []
            ok = [p for p in cands[0] if any(abs(q - (p + n)) <= 1 for q in nxt)]
            pick = ok[0] if ok else (cands[0][-1] if cands[0] else None)
            starts.append((pick, "matched" if pick else "unknown"))
            continue
        prev, prev_method = starts[-1]
        prev_n = chapters[k - 1]["chapter_number_of_pages"] or 1
        expected = prev + prev_n if prev else None
        # Skipping ahead is allowed (books omit some chapters); going back is not (TOC hits).
        later = [p for p in cands[k] if p >= (expected - 2 if expected else (prev or 0))]
        if later:
            starts.append((later[0], "matched"))
            continue
        if expected:
            starts.append((expected - 1 if expected > 1 else expected, "estimated"))
        elif later:
            starts.append((later[0], "matched"))
        else:
            starts.append((None, "unknown"))
    if starts[0][0] is None and len(starts) > 1 and starts[1][0]:
        starts[0] = (starts[1][0] - (chapters[0]["chapter_number_of_pages"] or 1), "estimated")
    return starts


def front_matter(pdf: fitz.Document) -> dict:
    """Copyright years and publisher from the title/copyright pages of an e-library volume."""
    text = " ".join(pdf[i].get_text() for i in range(min(6, len(pdf))))
    years = re.search(r"(?:©|Copyright)\s*©?\s*((?:\d{4}(?:,\s*)?)+)", text)
    publisher = re.search(r"Published by ([^\n]+)", text)
    return {
        "copyright_years": [int(y) for y in re.findall(r"\d{4}", years.group(1))] if years else [],
        "published_by": publisher.group(1).strip() if publisher else None,
    }


def main() -> None:
    cache = json.loads((ELIB / "cache" / "elibrary_cache.json").read_text(encoding="utf-8"))
    result: dict = {}
    for book in cache["books"]:
        pdf = fitz.open(ELIB / "sourcepdfs" / book["book_name"])
        pages = [norm(p.get_text()) for p in pdf]
        result.setdefault("_books", {})[str(book["book_number"])] = front_matter(pdf)
        chapters = book["book_chapters"]
        starts = choose_starts(chapters, [candidates(c, pages) for c in chapters])
        header_len = len(norm(book["book_title"]))
        for k, (ch, (first, method)) in enumerate(zip(chapters, starts)):
            n = ch["chapter_number_of_pages"] or 1
            last = min(first + n - 1, len(pdf)) if first else None
            nxt, nxt_method = starts[k + 1] if k + 1 < len(starts) else (None, "")
            contiguous = bool(last and nxt and nxt_method == "matched" and nxt <= first + n + 1)
            if contiguous:
                # contiguous: this chapter ends where the next one starts
                top = starts_at_top(chapters[k + 1], pages[nxt - 1], header_len)
                last = nxt - 1 if top else nxt
            elif first:
                # Not followed by an adjacent chapter: the page count includes reference lists and
                # trailing blank pages, so cap by it, drop blank pages, and require the body text end.
                chunks = ch.get("chapter_chunks") or []
                tail = norm(chunks[-1]["chunk_text"])[-60:] if chunks else ""
                body_end = next((i + 1 for i in range(first - 1, len(pages)) if tail and tail in pages[i]), None)
                if last and nxt and last > nxt:
                    last = nxt
                while last and last > first and is_blank(pages[last - 1], header_len):
                    last -= 1
                if body_end and last and body_end > last:
                    last = body_end
                contiguous = bool(body_end)
            result[f"{book['book_number']}.{ch['chapter_number']}"] = {
                "first": first,
                "last": last,
                "method": method,
                "last_estimated": not contiguous,
                "pdf_pages": len(pdf),
            }
        est = sum(1 for _, m in starts if m != "matched")
        print(f"book {book['book_number']:>2}: {len(chapters)} chapters, {est} not matched directly")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
