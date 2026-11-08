"""Build the csclbot search index (data/index/).

One index, one embedding model (intfloat/e5-base-v2, 768-dim):
  * e-library base-level chunks (17,441)   vectors reused from ../elibrary/vector_store/elibrary.faiss
  * e-library chapter summaries (335)      vectors reused from ../elibrary/vector_store/chapter_summaries.faiss
  * ijCSCL article summaries (~465)        embedded here: title + 50-60-word Haiku summary
Journal articles are indexed by title and short summary only, except the open-access articles with a
Creative Commons licence in the reference data (CC BY 4.0, CC BY-NC 2.0): their full text is added as
passages (about 150 words) with exact printed pages and the licence, read from the local Anniversary PDFs.

Every item carries the id of its record in data/references.json and, for book chunks, the book page
(located by matching the chunk text in the book PDF; the chunk page numbers stored in the old index
drift by 1-3 pages, so they are not used). Outputs (git-ignored, rebuildable):
  data/index/items.jsonl  data/index/vectors.npy  data/index/bm25/

Chunk text comes from ../elibrary/cache/elibrary_cache.pkl (the JSON export keeps only a 65-character
stub per chunk). Needs ../elibrary (read-only) and data/raw/elibrary_chapter_pages.json (src/locate_chapter_pages.py).
Run: .venv/bin/python src/build_index.py
"""
from __future__ import annotations

import glob
import json
import os
import pickle
import re
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import bm25s
import faiss
import numpy as np
import Stemmer

from anniversary_corpus import NOTICE
from build_keyword_index import body_pages, pdf_index
from index_common import INDEX_DIR, MODEL_NAME, PASSAGE_PREFIX

ROOT = Path(__file__).resolve().parent.parent
ELIB = ROOT.parent / "elibrary"
REFS = ROOT / "data" / "references.json"
IJCSCL = ROOT / "data" / "inputs" / "ijcscl.json"
CHAPTER_PAGES = ROOT / "data" / "raw" / "elibrary_chapter_pages.json"


class _Stub:
    """Stand-in for the E-Library cache classes, so its code is not needed to read the pickle."""

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)


class _Unpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        return _Stub if module.startswith("cache") or "elibrary_cache" in module else super().find_class(module, name)


def load_cache() -> dict:
    """Books -> chapters -> chunks / summaries from the pickle, as plain dicts."""
    with (ELIB / "cache" / "elibrary_cache.pkl").open("rb") as f:
        cache = _Unpickler(f).load()
    return {
        "books": [
            {
                "book_number": b.book_number,
                "book_chapters": [
                    {
                        "chapter_number": c.chapter_number,
                        "chapter_chunks": [
                            {"chunk_index": k.chunk_index, "chunk_level": k.chunk_level, "chunk_text": k.chunk_text}
                            for k in c.chapter_chunks
                        ],
                        "chapter_summaries": [{"chapter_summary_text": s.chapter_summary_text} for s in c.chapter_summaries],
                    }
                    for c in b.book_chapters
                ],
            }
            for b in cache.books
        ]
    }


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text.lower()))


class BookPages:
    """Normalized text of every page of one book PDF (page numbers are 1-based, as printed)."""

    def __init__(self, number: int):
        pdf = fitz.open(glob.glob(str(ELIB / "sourcepdfs" / f"{number}.*.pdf"))[0])
        self.pages = [norm(p.get_text()) for p in pdf]

    def find(self, key: str, lo: int, hi: int) -> int | None:
        return next((p for p in range(max(lo, 1), min(hi, len(self.pages)) + 1) if key in self.pages[p - 1]), None)


def locate(chunks: list[dict], book: BookPages, first: int, last: int, stats: dict) -> list[tuple[int, int]]:
    """(first page, last page) for each chunk of a chapter, found by matching its text in the PDF."""
    out, cur = [], first
    for c in chunks:
        text = norm(c["chunk_text"])
        start = book.find(text[10:45], cur, cur + 3) or book.find(text[10:45], first, last + 1)
        if start is None:
            stats["start_not_found"] += 1
            start = cur
        end = book.find(text[-45:-10], start, start + 2) or start
        out.append((start, end))
        cur = start
        stats["chunks"] += 1
    return out


def library_items(cache: dict, pages: dict) -> tuple[list[dict], list[int]]:
    """Base-level chunks and chapter summaries, with the row of their vector in the old FAISS files."""
    chapters = {(b["book_number"], c["chapter_number"]): c for b in cache["books"] for c in b["book_chapters"]}
    items, rows = [], []
    stats = {"chunks": 0, "start_not_found": 0}
    located: dict[tuple[int, int], list[tuple[int, int]]] = {}
    books: dict[int, BookPages] = {}

    meta = json.loads((ELIB / "vector_store" / "elibrary_meta.json").read_text(encoding="utf-8"))
    for row, m in sorted(((int(k), v) for k, v in meta.items())):
        if m["chunk_level"] != 0:
            continue
        bn, cn = m["book_number"], m["chapter_number"]
        key = f"{bn}.{cn}"
        if (bn, cn) not in located:
            books.setdefault(bn, BookPages(bn))
            ch_chunks = [c for c in chapters[(bn, cn)]["chapter_chunks"] if c["chunk_level"] == 0]
            located[(bn, cn)] = locate(ch_chunks, books[bn], pages[key]["first"], pages[key]["last"], stats)
        chunk = chapters[(bn, cn)]["chapter_chunks"][m["chunk_index"]]
        start, end = located[(bn, cn)][m["chunk_index"]]
        items.append({"kind": "chunk", "doc_id": f"elibrary:{key}", "page": start, "page_end": end, "text": chunk["chunk_text"]})
        rows.append(row)
    n_chunks = len(items)
    print(f"pages located for {stats['chunks']} chunks; {stats['start_not_found']} not found (previous chunk's page used)")

    sm = json.loads((ELIB / "vector_store" / "chapter_summaries_meta.json").read_text(encoding="utf-8"))
    summary_rows = []
    for row, m in sorted(((int(k), v) for k, v in sm.items())):
        ch = chapters[(m["book_number"], m["chapter_number"])]
        text = ch["chapter_summaries"][0]["chapter_summary_text"] if ch["chapter_summaries"] else ""
        items.append({"kind": "chapter_summary", "doc_id": f"elibrary:{m['book_number']}.{m['chapter_number']}", "page": None, "text": text})
        summary_rows.append(row)
    print(f"{n_chunks} chunks, {len(summary_rows)} chapter summaries from the e-library")
    return items, rows + summary_rows


def article_items(refs: dict) -> list[dict]:
    articles = json.loads(IJCSCL.read_text(encoding="utf-8"))
    ref_ids = {d["corpus"]["record_id"]: d["id"] for d in refs["documents"] if d["id"].startswith("ijcscl:")}
    items = []
    for rec_id, rec in articles.items():
        summary = (rec.get("summary_haiku") or "").strip()
        title = ref_title(refs, ref_ids[rec_id])
        if not summary or NOTICE.search(title):
            continue
        items.append({"kind": "article_summary", "doc_id": ref_ids[rec_id], "page": None, "text": f"{title}. {summary}"})
    print(f"{len(items)} ijCSCL article summaries")
    return items


CHUNK_WORDS, CHUNK_STRIDE = 150, 120


def strip_running_text(pages: list[str]) -> list[list[str]]:
    """Lines per page without running heads and bare page numbers (lines repeated on >= 35% of the pages)."""
    lines = [[ln.strip() for ln in text.splitlines() if ln.strip()] for text in pages]
    seen: dict[str, int] = {}
    for page in lines:
        for ln in set(page):
            seen[ln] = seen.get(ln, 0) + 1
    limit = max(3, int(0.35 * len(pages)))
    return [[ln for ln in page if not (seen[ln] >= limit and len(ln) < 120) and not ln.isdigit()] for page in lines]


def join_hyphenated(tokens: list[str], page: int) -> list[tuple[str, int]]:
    """'sand-' 'stone' -> 'sandstone': the typesetter's line-break hyphens (hyphen at the end of a token)."""
    out: list[tuple[str, int]] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.endswith("-") and len(t) > 2 and t[-2].isalpha() and i + 1 < len(tokens) and tokens[i + 1][:1].islower():
            out.append((t[:-1] + tokens[i + 1], page))
            i += 2
        else:
            out.append((t, page))
            i += 1
    return out


def open_access_items(refs: dict) -> list[dict]:
    """Full-text passages of the articles with a Creative Commons licence, with exact printed pages."""
    files = pdf_index()
    items = []
    for d in refs["documents"]:
        if not d["id"].startswith("ijcscl:") or not d.get("license") or not d.get("pages") or NOTICE.search(d["title"]):
            continue
        pdf_file = files.get(d["corpus"]["record_id"])
        first, last = int(d["pages"]["first"]), int(d["pages"]["last"])
        if pdf_file is None:
            continue
        pdf = fitz.open(pdf_file)
        if len(pdf) != last - first + 1:
            continue
        words: list[tuple[str, int]] = []
        for offset, page in enumerate(strip_running_text(body_pages(pdf))):
            words += join_hyphenated([w for ln in page for w in ln.split()], first + offset)
        for start in range(0, max(len(words) - 40, 1), CHUNK_STRIDE):
            window = words[start : start + CHUNK_WORDS]
            if sum(any(c.isdigit() for c in w) for w, _ in window) > 0.3 * len(window):  # table fragments
                continue
            items.append(
                {
                    "kind": "chunk",
                    "doc_id": d["id"],
                    "page": window[0][1],
                    "page_end": window[-1][1],
                    "text": " ".join(w for w, _ in window),
                    "license": d["license"]["name"],
                }
            )
    print(f"{len(items)} passages from {len({i['doc_id'] for i in items})} open-access articles")
    return items


def ref_title(refs: dict, doc_id: str) -> str:
    return next(d["title"] for d in refs["documents"] if d["id"] == doc_id)


def main() -> None:
    from sentence_transformers import SentenceTransformer

    refs = json.loads(REFS.read_text(encoding="utf-8"))
    cache = load_cache()
    pages = json.loads(CHAPTER_PAGES.read_text(encoding="utf-8"))
    known = {d["id"] for d in refs["documents"]}

    lib, rows = library_items(cache, pages)
    n_chunks = sum(i["kind"] == "chunk" for i in lib)
    old_chunks = faiss.read_index(str(ELIB / "vector_store" / "elibrary.faiss"))
    old_summaries = faiss.read_index(str(ELIB / "vector_store" / "chapter_summaries.faiss"))
    vec_chunks = np.vstack([old_chunks.reconstruct(r) for r in rows[:n_chunks]])
    vec_summaries = np.vstack([old_summaries.reconstruct(r) for r in rows[n_chunks:]])

    arts = article_items(refs)
    model = SentenceTransformer(MODEL_NAME)
    vec_arts = model.encode([PASSAGE_PREFIX + a["text"] for a in arts], normalize_embeddings=True, batch_size=32, show_progress_bar=False)

    oa = open_access_items(refs)
    vec_oa = model.encode([PASSAGE_PREFIX + i["text"] for i in oa], normalize_embeddings=True, batch_size=32, show_progress_bar=False)

    items = lib + arts + oa
    vectors = np.vstack([vec_chunks, vec_summaries, vec_arts, vec_oa]).astype("float32")
    missing = {i["doc_id"] for i in items} - known
    assert not missing, f"items without a reference record: {sorted(missing)[:5]}"
    assert len(items) == len(vectors)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_DIR / "vectors.npy", vectors)
    with (INDEX_DIR / "items.jsonl").open("w", encoding="utf-8") as f:
        for n, item in enumerate(items):
            f.write(json.dumps({"n": n, **item}, ensure_ascii=False) + "\n")

    stemmer = Stemmer.Stemmer("english")
    tokens = bm25s.tokenize([i["text"] for i in items], stopwords="en", stemmer=stemmer, show_progress=False)
    bm25 = bm25s.BM25()
    bm25.index(tokens, show_progress=False)
    bm25.save(str(INDEX_DIR / "bm25"))
    print(f"index built: {len(items)} items, {vectors.shape[1]}-dim, {vectors.nbytes / 1e6:.0f} MB of vectors")


if __name__ == "__main__":
    main()
