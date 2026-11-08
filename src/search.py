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
KW_MAX_PAGES = 2000      # pages retrieved from the keyword index (all matches for a rare term)
KW_TOP_DOCS = 12         # articles with a keyword item when the term is common
KW_RARE_DOCS = 60        # at most this many matching articles = a rare term: list the earliest too
KW_WEIGHT = 1.5          # the keyword index is the only view of the article bodies, so it counts a little more
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
        self.summary_by_doc = {i["doc_id"]: i for i in self.items if i["kind"] == "article_summary"}
        self.kw = self.kw_pages = None
        if (INDEX_DIR / "kw_bm25").exists():  # page-level keyword index of the articles (no text)
            self.kw = bm25s.BM25.load(str(INDEX_DIR / "kw_bm25"))
            self.kw_pages = [json.loads(line) for line in (INDEX_DIR / "kw_pages.jsonl").open(encoding="utf-8")]

    def page_scores(self, tokens: list[str]) -> dict[str, list[tuple[float, int]]]:
        """doc_id -> [(score, printed page)] for the pages that match at least one of the (stemmed) tokens."""
        k = min(KW_MAX_PAGES, len(self.kw_pages))
        try:
            hits, scores = self.kw.retrieve([tokens], k=k, show_progress=False)
        except Exception:  # none of the tokens is in the index
            return {}
        per_doc: dict[str, list[tuple[float, int]]] = defaultdict(list)
        for i, score in zip(hits[0], scores[0]):
            if score > 0:
                page = self.kw_pages[int(i)]
                per_doc[page["doc_id"]].append((float(score), page["page"]))
        return per_doc

    def keyword_items(self, query: str) -> tuple[list[dict], dict | None]:
        """One item per article with the pages where the query words occur, best first. If the rarest query
        word occurs in only a few articles (e.g. "squib"), those articles are listed and an overview with
        the years is returned, so "when" questions can be answered. Only page numbers are known, never text."""
        if self.kw is None:
            return [], None
        words = bm25s.tokenize(query, stopwords="en", stemmer=self.stemmer, return_ids=False, show_progress=False)[0]
        words = list(dict.fromkeys(words))
        original = {self.stemmer.stemWord(w): w for w in re.findall(r"[A-Za-z0-9]+", query.lower())}  # stem -> word as typed
        per_word = {w: self.page_scores([w]) for w in words}
        rare_word = min((w for w in words if per_word[w]), key=lambda w: len(per_word[w]), default=None)
        rare = rare_word is not None and len(per_word[rare_word]) <= KW_RARE_DOCS
        per_doc = per_word[rare_word] if rare else self.page_scores(words)
        ranked = sorted(per_doc, key=lambda d: -max(sc for sc, _ in per_doc[d]))
        if not ranked:
            return [], None
        years = sorted(self.refs[d]["year"] for d in ranked)
        overview = {"n": len(ranked), "first": years[0], "last": years[-1], "ranked": ranked, "word": original.get(rare_word, rare_word)} if rare else None
        items = []
        for doc_id in ranked if rare else ranked[:KW_TOP_DOCS]:
            pages = sorted(p for _, p in sorted(per_doc[doc_id], reverse=True)[:6])
            shown = f"the word \"{original.get(rare_word, rare_word)}\"" if rare else "words from the question (" + ", ".join(original.get(w, w) for w in words) + ")"
            text = f"Keyword match: {shown} occurs on page(s) {format_runs(pages)} of this article. Its text is not available here, only this summary."
            if overview:
                text += f" The word occurs in {overview['n']} article(s) in all, published {overview['first']}-{overview['last']}."
            # pages are shown (and cited) only when a distinctive word drives the match; for common words
            # the keyword index only helps the ranking
            items.append({"kind": "article_pages", "doc_id": doc_id, "page": pages[0], "page_end": pages[-1], "pages_list": pages, "text": text, "show": rare})
        return items, overview

    def rank_items(self, query: str) -> tuple[list[tuple[float, dict]], dict | None]:
        q = self.model.encode(QUERY_PREFIX + query, normalize_embeddings=True)
        dense = np.argsort(-(self.vectors @ q))[:CANDIDATES]
        tokens = bm25s.tokenize(query, stopwords="en", stemmer=self.stemmer, show_progress=False)
        hits, scores = self.bm25.retrieve(tokens, k=CANDIDATES, show_progress=False)
        sparse = [int(i) for i, s in zip(hits[0], scores[0]) if s > 0]
        fused: dict = defaultdict(float)
        items: dict = {}
        for ranking in (dense.tolist(), sparse):
            for rank, n in enumerate(ranking, 1):
                fused[n] += 1.0 / (RRF_K + rank)
                items[n] = self.items[n]
        kw_items, overview = self.keyword_items(query)
        for rank, item in enumerate(kw_items, 1):
            key = ("kw", item["doc_id"])
            fused[key] += KW_WEIGHT / (RRF_K + rank)
            items[key] = item
        return [(fused[k], items[k]) for k in fused], overview

    def search(self, query: str, books: int = 5, articles: int = 4, per_doc: int = 2) -> list[dict]:
        """Best book/chapter documents and best ijCSCL articles, ranked separately (17,000 book chunks
        would otherwise crowd out the 460 article summaries). Results carry group 'book' or 'article'.
        For a rare term the two earliest matching articles are added, so "when" questions can be answered."""
        ranked_items, overview = self.rank_items(query)
        by_doc: dict[str, list[tuple[float, dict]]] = defaultdict(list)
        for score, item in ranked_items:
            by_doc[item["doc_id"]].append((score, item))
        scored = []
        for doc_id, hits in by_doc.items():
            hits.sort(key=lambda h: -h[0])
            # best item plus a damped bonus for further hits in the same document
            scored.append((hits[0][0] + 0.3 * sum(s for s, _ in hits[1:3]), doc_id, hits))
        scored.sort(key=lambda t: -t[0])
        by_id = {t[1]: t for t in scored}
        earliest: list[str] = []
        if overview:
            earliest = sorted(overview["ranked"], key=lambda d: (self.refs[d]["year"], self.refs[d]["pages"]["first"] if self.refs[d].get("pages") else "0"))
        out = []
        for group, limit in (("book", books), ("article", articles)):
            picked = [t for t in scored if t[1].startswith("ijcscl:") == (group == "article")][:limit]
            if group == "article" and overview:
                picked += [by_id[d] for d in earliest[:2] if d in by_id and by_id[d] not in picked]
            for score, doc_id, hits in picked:
                if group == "article" and doc_id in self.summary_by_doc and not any(i["kind"] == "article_summary" for _, i in hits):
                    hits = hits + [(0.0, self.summary_by_doc[doc_id])]  # say what the article is about
                out.append({**self.result(doc_id, hits, score, per_doc), "group": group})
        if overview:
            earliest_cites = [r["cite"] for r in out if r["id"] in earliest[:2]]
            note = (f"Search note: a full-text keyword search found the word \"{overview['word']}\" in {overview['n']} article(s) published "
                    f"{overview['first']}-{overview['last']}. The earliest of them: {'; '.join(earliest_cites)}. "
                    "The word does occur on those pages, but the articles' text is not available, so what they say about it is unknown.")
            next(r for r in out if r["group"] == "article")["note"] = note
        return out

    def result(self, doc_id: str, hits: list[tuple[float, dict]], score: float, per_doc: int) -> dict:
        doc = self.refs[doc_id]
        hits = [h for h in hits if h[1].get("show", True)]
        snippets = [snippet(item) for _, item in hits[:per_doc]]
        pages = cited_pages(doc, [item for _, item in hits[:per_doc]])
        return {
            "id": doc_id,
            "type": doc["type"],
            "score": score,
            "cite": in_text(doc, pages),
            "cite_short": doc["cite_short"],
            "title": doc["title"],
            "reference": doc["apa"],
            "pages": pages,
            "snippets": snippets,
            "passages": [
                {"kind": item["kind"], "text": re.sub(r"\s+", " ", item["text"]).strip(), "cite": in_text(doc, cited_pages(doc, [item])), "pages": cited_pages(doc, [item])}
                for _, item in hits[:per_doc]
            ],
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
    pages = {p for i in items if i["kind"] == "chunk" for p in range(i["page"], i["page_end"] + 1)}
    pages |= {p for i in items if i["kind"] == "article_pages" for p in i["pages_list"]}
    return format_runs(sorted(pages), limit=4) if pages else whole_pages(doc)


def format_runs(pages: list[int], limit: int | None = None) -> str:
    """[244, 245, 250] -> '244–245, 250' (at most `limit` runs, then ' …')."""
    runs, start = [], pages[0]
    for prev, cur in zip(pages, pages[1:] + [None]):
        if cur != prev + 1:
            runs.append(str(start) if start == prev else f"{start}–{prev}")
            start = cur
    shown = runs if limit is None else runs[:limit]
    return ", ".join(shown) + (" …" if limit is not None and len(runs) > limit else "")


def in_text(doc: dict, pages: str | None) -> str:
    if not pages:
        return f"({doc['cite_short']})"
    label = "pp." if re.search(r"[–,]", pages) else "p."
    return f"({doc['cite_short']}, {label} {pages})"


def format_results(query: str, results: list[dict]) -> str:
    lines = [f"## {query}", ""]
    headings = {"book": "Book chapters (Stahl e-library)", "article": "ijCSCL articles (summaries; keyword matches give exact pages)"}
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
