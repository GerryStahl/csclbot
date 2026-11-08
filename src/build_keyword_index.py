"""Build the page-level keyword index of the ijCSCL articles (data/index/kw_bm25, kw_pages.jsonl).

For every article page the index keeps only a bag of stemmed words with BM25 weights: which words
occur on which page, never the text or the word order, so the text cannot be reconstructed or quoted.
Reference lists are cut off first, so cited titles do not match. The text is read from the local
Anniversary PDFs (read-only, never copied); printed page = first page of the article + PDF page index
(true for 469 of 470 articles; the other has no page range and is skipped).

Output (git-ignored, rebuildable, shipped in the image with the rest of data/index/):
  data/index/kw_bm25/    BM25 weights per page and the word list (no corpus text)
  data/index/kw_pages.jsonl   one line per page: doc_id (references.json id) and printed page

Run: .venv/bin/python src/build_keyword_index.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import bm25s
import fitz  # PyMuPDF
import Stemmer

from anniversary_corpus import NOTICE
from index_common import INDEX_DIR

ROOT = Path(__file__).resolve().parent.parent
ANNIVERSARY = ROOT.parent / "anniversary" / "data"
REFS = ROOT / "data" / "references.json"
REFERENCES_HEADING = re.compile(r"^\W*(?:references|reference list|bibliography)\W*$", re.I | re.M)


def pdf_index() -> dict[str, Path]:
    return {f.stem: f for d in (ANNIVERSARY / "raw 2006-2015", ANNIVERSARY / "raw 2016-2026") for f in d.glob("*.pdf")}


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # Springer PDFs encode curly quotes as B...^ (e.g. "Bsquib^")
    return re.sub(r"\bB(\w[\w \-]{0,40}?)\^", r"\1", text)


def body_pages(pdf: fitz.Document) -> list[str]:
    """Page texts with the reference list removed (the last 'References' heading in the second half)."""
    texts = [clean(p.get_text()) for p in pdf]
    cut_page, cut_pos = None, 0
    for i in range(len(texts) // 2, len(texts)):
        m = list(REFERENCES_HEADING.finditer(texts[i]))
        if m:
            cut_page, cut_pos = i, m[-1].start()
    if cut_page is None:
        return texts
    return texts[:cut_page] + [texts[cut_page][:cut_pos]]


def main() -> None:
    refs = json.loads(REFS.read_text(encoding="utf-8"))["documents"]
    files = pdf_index()
    pages: list[dict] = []
    texts: list[str] = []
    skipped = 0
    for d in refs:
        if not d["id"].startswith("ijcscl:") or NOTICE.search(d["title"]):
            continue
        pdf_file = files.get(d["corpus"]["record_id"])
        if pdf_file is None or not d.get("pages"):
            skipped += 1
            continue
        first, last = int(d["pages"]["first"]), int(d["pages"]["last"])
        pdf = fitz.open(pdf_file)
        if len(pdf) != last - first + 1:  # page numbers could not be trusted
            skipped += 1
            continue
        for offset, text in enumerate(body_pages(pdf)):
            if len(text.split()) >= 20:
                pages.append({"doc_id": d["id"], "page": first + offset})
                texts.append(text)
    print(f"{len(pages)} pages from {len({p['doc_id'] for p in pages})} articles; {skipped} articles skipped")

    stemmer = Stemmer.Stemmer("english")
    tokens = bm25s.tokenize(texts, stopwords="en", stemmer=stemmer, show_progress=False)
    index = bm25s.BM25()
    index.index(tokens, show_progress=False)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    index.save(str(INDEX_DIR / "kw_bm25"))  # no corpus argument: the page text is not saved
    with (INDEX_DIR / "kw_pages.jsonl").open("w", encoding="utf-8") as f:
        for n, p in enumerate(pages):
            f.write(json.dumps({"n": n, **p}) + "\n")
    print("keyword index saved")


if __name__ == "__main__":
    main()
