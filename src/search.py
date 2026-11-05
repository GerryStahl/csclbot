"""Hybrid search over the csclbot index with APA references (step 4: retrieval only, no LLM).

Dense (e5-base-v2) and BM25 rankings over all items are merged by reciprocal rank fusion, then
grouped by document. Each result gives the in-text citation with page(s), the APA reference, short
snippets, and every linked reference (the journal article and its book-chapter reprint, the original
publication), because different users may have access to different sources.

Run: .venv/bin/python src/search.py "How does group cognition differ from individual cognition?" [-b 5] [-a 4]
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import bm25s
import numpy as np
import Stemmer

from index_common import INDEX_DIR, MODEL_NAME, QUERY_PREFIX

REFS = Path(__file__).resolve().parent.parent / "data" / "references.json"
RRF_K = 60
CANDIDATES = 200
SNIPPET_CHARS = 380
RELATION_LABELS = {
    "reprint_of": "Also published as",
    "reprinted_in": "Also reprinted as",
    "originally_published_as": "Original publication",
    "original_of": "Reprinted/collected as",
    "same_text_as": "Same text also in",
}


class Searcher:
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.items = [json.loads(line) for line in (INDEX_DIR / "items.jsonl").open(encoding="utf-8")]
        self.vectors = np.load(INDEX_DIR / "vectors.npy")
        self.bm25 = bm25s.BM25.load(str(INDEX_DIR / "bm25"))
        self.stemmer = Stemmer.Stemmer("english")
        self.model = SentenceTransformer(MODEL_NAME)
        self.refs = {d["id"]: d for d in json.loads(REFS.read_text(encoding="utf-8"))["documents"]}

    def rank_items(self, query: str) -> dict[int, float]:
        q = self.model.encode(QUERY_PREFIX + query, normalize_embeddings=True)
        dense = np.argsort(-(self.vectors @ q))[:CANDIDATES]
        tokens = bm25s.tokenize(query, stopwords="en", stemmer=self.stemmer, show_progress=False)
        hits, scores = self.bm25.retrieve(tokens, k=CANDIDATES, show_progress=False)
        sparse = [int(i) for i, s in zip(hits[0], scores[0]) if s > 0]
        fused: dict[int, float] = defaultdict(float)
        for ranking in (dense.tolist(), sparse):
            for rank, n in enumerate(ranking, 1):
                fused[n] += 1.0 / (RRF_K + rank)
        return fused

    def search(self, query: str, books: int = 5, articles: int = 4, per_doc: int = 2) -> list[dict]:
        """Best book/chapter documents and best ijCSCL articles, ranked separately (17,000 book chunks
        would otherwise crowd out the 460 article summaries). Results carry group 'book' or 'article'."""
        fused = self.rank_items(query)
        by_doc: dict[str, list[tuple[float, dict]]] = defaultdict(list)
        for n, score in fused.items():
            item = self.items[n]
            by_doc[item["doc_id"]].append((score, item))
        scored = []
        for doc_id, hits in by_doc.items():
            hits.sort(key=lambda h: -h[0])
            # best item plus a damped bonus for further hits in the same document
            scored.append((hits[0][0] + 0.3 * sum(s for s, _ in hits[1:3]), doc_id, hits))
        scored.sort(key=lambda t: -t[0])
        out = []
        for group, limit in (("book", books), ("article", articles)):
            picked = [t for t in scored if t[1].startswith("ijcscl:") == (group == "article")][:limit]
            out += [{**self.result(doc_id, hits, score, per_doc), "group": group} for score, doc_id, hits in picked]
        return out

    def result(self, doc_id: str, hits: list[tuple[float, dict]], score: float, per_doc: int) -> dict:
        doc = self.refs[doc_id]
        snippets = [snippet(item) for _, item in hits[:per_doc]]
        pages = cited_pages(doc, [item for _, item in hits[:per_doc]])
        return {
            "id": doc_id,
            "type": doc["type"],
            "score": score,
            "cite": in_text(doc, pages),
            "reference": doc["apa"],
            "pages": pages,
            "snippets": snippets,
            "also": [
                {"label": RELATION_LABELS[r["relation"]], "id": r["id"], "reference": self.refs[r["id"]]["apa"], "cite": in_text(self.refs[r["id"]], whole_pages(self.refs[r["id"]]))}
                for r in doc["related"]
                if r["relation"] in RELATION_LABELS
            ],
        }


def snippet(item: dict) -> str:
    text = re.sub(r"\s+", " ", item["text"]).strip()
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rsplit(" ", 1)[0] + " …"


def whole_pages(doc: dict) -> str | None:
    return doc["pages"]["display"] if doc.get("pages") else None


def cited_pages(doc: dict, items: list[dict]) -> str | None:
    """Pages of the displayed chunks for book chapters; the whole page range for articles and summaries."""
    chunk_pages = sorted({p for i in items if i["kind"] == "chunk" for p in range(i["page"], i["page_end"] + 1)})
    if not chunk_pages:
        return whole_pages(doc)
    runs, start = [], chunk_pages[0]
    for prev, cur in zip(chunk_pages, chunk_pages[1:] + [None]):
        if cur != prev + 1:
            runs.append(str(start) if start == prev else f"{start}–{prev}")
            start = cur
    return ", ".join(runs[:4]) + (" …" if len(runs) > 4 else "")


def in_text(doc: dict, pages: str | None) -> str:
    if not pages:
        return f"({doc['cite_short']})"
    label = "pp." if re.search(r"[–,]", pages) else "p."
    return f"({doc['cite_short']}, {label} {pages})"


def format_results(query: str, results: list[dict]) -> str:
    lines = [f"## {query}", ""]
    headings = {"book": "Book chapters (Stahl e-library)", "article": "ijCSCL articles (summaries; pages are the whole article)"}
    n = 0
    for group in ("book", "article"):
        part = [r for r in results if r["group"] == group]
        if not part:
            continue
        lines += [f"### {headings[group]}", ""]
        for r in part:
            n += 1
            lines += [f"**{n}. {r['cite']}** — {r['type'].replace('_', ' ')}", "", f"   {r['reference']}", ""]
            for snip in r["snippets"]:
                lines.append(f"   > {snip}")
            for a in r["also"]:
                lines += ["", f"   *{a['label']}:* {a['reference']}"]
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("query")
    parser.add_argument("-b", "--books", type=int, default=5, help="number of book-chapter results")
    parser.add_argument("-a", "--articles", type=int, default=4, help="number of ijCSCL article results")
    args = parser.parse_args()
    print(format_results(args.query, Searcher().search(args.query, books=args.books, articles=args.articles)))


if __name__ == "__main__":
    main()
