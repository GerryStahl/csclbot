"""Answer a question with Claude, grounded in the retrieved passages, with APA citations (step 5).

Pipeline: search (src/search.py) -> numbered sources [S1]... -> Claude answers using only those
sources and tags claims with [S#] -> the program replaces each tag by the source's in-text citation
(e.g. "(Stahl, 2026, p. 245)") and appends full APA references for the sources actually cited,
together with alternative sources (journal version / book reprint / original publication).
Journal articles are represented only by their short summaries, so they are paraphrased, not quoted.

Follow-up questions: ask(..., history=[{"q": ..., "a": ...}]) first rewrites the question into a standalone
one (a short Haiku call) so the search understands "that" or "the second one", then answers with the last turns
as context. Citations always come from the current turn's sources.

Needs ANTHROPIC_API_KEY in the environment (never in the code or the repo).
Run: .venv/bin/python src/answer.py "How is group cognition different from individual cognition?"
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import anthropic

from search import Searcher

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 900
QUOTE_LIMIT_WORDS = 25
HISTORY_TURNS = 3          # earlier question/answer pairs given to the model
HISTORY_ANSWER_CHARS = 1200
REWRITE_MAX_TOKENS = 120

REWRITE_SYSTEM = (
    "Rewrite the user's last question as ONE standalone question that can be understood without the conversation, "
    "to search a library on computer-supported collaborative learning. Resolve references such as 'that', 'it', "
    "'those studies' or 'the second one' using the conversation, and keep the user's key terms. If the last question "
    "is already standalone or starts a new topic, return it unchanged. Output only the question."
)

SYSTEM = f"""You are csclbot, a research assistant for the field of computer-supported collaborative learning (CSCL). \
You answer questions using ONLY the numbered sources supplied in the user message: passages from Gerry Stahl's \
books and chapters, passages from open-access articles in the International Journal of Computer-Supported \
Collaborative Learning (ijCSCL), and short summaries of the other ijCSCL articles.

Rules:
- Ground every claim in the sources and mark it with the source tag in square brackets, e.g. [S3] or [S2, S5]. \
Use only tags that appear in the sources. Do not write author names, years or page numbers yourself; the tags are \
converted to citations automatically. Put each tag at the END of the sentence or clause it supports, never as its \
grammatical subject (write "Group cognition is publicly visible [S1]", not "[S1] argues that ...").
- If the sources do not answer the question, or only partly, say so plainly and answer only what they support. \
Never fill gaps from memory.
- Paraphrase. Quote at most {QUOTE_LIMIT_WORDS} consecutive words from a passage, in quotation marks, exactly as \
written and as one continuous stretch (no ellipses inside a quotation). Article sources are summaries: never use \
quotation marks for words taken from them, and do not claim details beyond what the summary says.
- A "keyword match" source only says that the search words occur on the listed pages of an article; it gives no \
text. You may say that the words occur there, using the citation, but never claim what the article says about \
them beyond that article's summary and the book passages.
- If the sources include a "Search note", report it: say that the word occurs in that many articles, name the \
earliest ones with their citations, and state plainly what the sources do not show (what those articles say about \
it). For "when" or "first" questions use the publication years, and say that this reflects the sources found.
- Where sources show different positions, say so. Write for a researcher: clear, precise, about 150-350 words, \
no headings, no bullet lists unless the question asks for a list.
- If a conversation so far is shown, it is context only: you may build on or refer to your earlier answers, but \
every new claim needs a tag from the CURRENT sources, and earlier citations must not be repeated as tags. Answer \
the latest question without repeating the earlier answers.
- Answer in the user's language only if it is English; otherwise reply in English."""

TAG = re.compile(r"\[(S\d+(?:\s*[,;]\s*S\d+)*)\]")


def build_sources(results: list[dict]) -> list[dict]:
    """Flatten results into numbered passages S1..Sn, each with its own citation."""
    sources = []
    for r in results:
        for p in r["passages"]:
            sources.append({**p, "n": len(sources) + 1, "doc": r})
    return sources


def format_sources(sources: list[dict]) -> str:
    blocks = []
    for s in sources:
        what = {
            "chunk": f"{s['doc']['type'].replace('_', ' ')}, passage",
            "chapter_summary": "book chapter, summary of the whole chapter",
            "article_summary": f"{s['doc']['type'].replace('_', ' ')}, short summary (do not quote)",
            "article_pages": f"{s['doc']['type'].replace('_', ' ')}, keyword match: page numbers only, no text",
        }[s["kind"]]
        blocks.append(f"[S{s['n']}] {s['cite']} — {what}\n{s['text']}")
    return "\n\n".join(blocks)


def format_notes(results: list[dict]) -> str:
    """Search notes (e.g. how many articles contain a rare word and which are earliest) for the model."""
    notes = [r["note"] for r in results if r.get("note")]
    return ("\n\n" + "\n".join(notes)) if notes else ""


def merge_pages(page_strings: list[str]) -> str:
    """Union of page strings such as '244–257' and '244' -> '244–257'."""
    spans = sorted((int(a), int(b or a)) for ps in page_strings for a, b in re.findall(r"(\d+)(?:–(\d+))?", ps))
    merged: list[list[int]] = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return ", ".join(str(lo) if lo == hi else f"{lo}–{hi}" for lo, hi in merged)


def year_suffixes(cited: list[dict]) -> dict[str, str]:
    """APA 2026a/2026b: documents with the same author-year get letters, ordered by title."""
    docs = {s["doc"]["id"]: s["doc"] for s in cited}
    groups: dict[str, list[dict]] = {}
    for d in docs.values():
        groups.setdefault(d["cite_short"], []).append(d)
    out = {}
    for members in groups.values():
        if len(members) > 1:
            for letter, d in zip("abcdefghij", sorted(members, key=lambda d: d["title"].lower())):
                out[d["id"]] = letter
    return out


def doc_cite(doc: dict, suffix: str, pages: list[str]) -> str:
    short = re.sub(r"(\d{4})$", lambda m: m.group(1) + suffix, doc["cite_short"])
    merged = merge_pages([p for p in pages if p])
    if not merged:
        return short
    return f"{short}, {'pp.' if re.search(r'[–,]', merged) else 'p.'} {merged}"


def link_citations(answer: str, sources: list[dict]) -> tuple[str, list[dict], dict[str, str]]:
    """Replace [S#] tags by APA in-text citations; return the text, cited sources and year suffixes."""
    by_n = {s["n"]: s for s in sources}
    cited: list[dict] = []
    for tag in TAG.findall(answer):
        for n in map(int, re.findall(r"\d+", tag)):
            if n in by_n and by_n[n] not in cited:
                cited.append(by_n[n])
    suffix = year_suffixes(cited)

    def repl(m: re.Match) -> str:
        per_doc: dict[str, list[dict]] = {}
        for n in map(int, re.findall(r"\d+", m.group(1))):
            if n in by_n:
                per_doc.setdefault(by_n[n]["doc"]["id"], []).append(by_n[n])
        cites = [doc_cite(v[0]["doc"], suffix.get(k, ""), [s["pages"] for s in v]) for k, v in per_doc.items()]
        return "(" + "; ".join(cites) + ")" if cites else ""

    return TAG.sub(repl, answer), cited, suffix


def references_block(cited: list[dict], suffix: dict[str, str]) -> str:
    docs: dict[str, dict] = {}
    for s in cited:
        docs.setdefault(s["doc"]["id"], s["doc"])
    entries = []
    for d in docs.values():
        ref = d["reference"]
        if d["id"] in suffix:
            ref = re.sub(r"\((\d{4})\)", lambda m: f"({m.group(1)}{suffix[d['id']]})", ref, count=1)
        entries.append((ref, d))
    lines = ["**References**", ""]
    for ref, d in sorted(entries, key=lambda e: e[0]):
        lines.append(f"- {ref}")
        if d.get("license"):
            lines.append(f"  - *Open access, {d['license']['name']}:* {d['license']['url']}")
        for a in d["also"]:
            lines.append(f"  - *{a['label']}:* {a['reference']}")
    return "\n".join(lines)


def strip_headings(text: str) -> str:
    """The prompt asks for no headings; drop the '#' markers if the model adds one anyway."""
    return re.sub(r"(?m)^#{1,6}\s+", "", text)


def norm_quote(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"[^a-z0-9']+", " ", text.lower()).strip()


def check_quotes(raw_answer: str, sources: list[dict]) -> list[str]:
    """Quotations (4+ words) that do not occur verbatim in any source, or that exceed the length cap."""
    haystack = " ".join(norm_quote(s["text"]) for s in sources if s["kind"] != "article_summary")
    summaries = " ".join(norm_quote(s["text"]) for s in sources if s["kind"] == "article_summary")
    problems = []
    marks = [m.start() for m in re.finditer(r"[\u201c\u201d\"]", raw_answer)]
    # quotation marks pair up in order (1st-2nd, 3rd-4th); a short quoted term must not shift the pairing
    for open_at, close_at in zip(marks[0::2], marks[1::2]):
        q = raw_answer[open_at + 1 : close_at]
        if len(q) < 12:
            continue
        if re.search(r"\.\.\.|\u2026", q):
            problems.append(f"ellipsis inside a quotation: \"{q[:70]}\"")
            continue
        words = len(q.split())
        if words < 4:
            continue
        if norm_quote(q) in haystack:
            if words > QUOTE_LIMIT_WORDS:
                problems.append(f"quotation of {words} words: \"{q[:60]}…\"")
        elif norm_quote(q) in summaries:
            problems.append(f"quotes an article summary: \"{q[:70]}\"")
        else:
            problems.append(f"not found in sources: \"{q[:70]}\"")
    return problems


def format_history(history: list[dict]) -> str:
    turns = history[-HISTORY_TURNS:]
    return "\n\n".join(f"Q: {h['q']}\nA: {h['a'][:HISTORY_ANSWER_CHARS]}" for h in turns)


def rewrite_query(client: anthropic.Anthropic, question: str, history: list[dict], model: str) -> tuple[str, list[int]]:
    """Standalone form of a follow-up question; unchanged (and no API call) when there is no history."""
    if not history:
        return question, [0, 0]
    msg = client.messages.create(
        model=model,
        max_tokens=REWRITE_MAX_TOKENS,
        system=REWRITE_SYSTEM,
        messages=[{"role": "user", "content": f"Conversation:\n{format_history(history)}\n\nLast question: {question}"}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip().strip('"')
    standalone = text if 0 < len(text) <= 400 else question
    return standalone, [msg.usage.input_tokens, msg.usage.output_tokens]


def user_message(sources: list[dict], results: list[dict], question: str, standalone: str, history: list[dict]) -> str:
    parts = []
    if history:
        parts.append(f"Conversation so far (context only):\n{format_history(history)}")
    parts.append(f"Sources:\n\n{format_sources(sources)}{format_notes(results)}")
    parts.append(f"Question: {question}" + (f"\n(Searched for: {standalone})" if standalone != question else ""))
    return "\n\n".join(parts)


def ask(question: str, searcher: Searcher, model: str = DEFAULT_MODEL, books: int = 5, articles: int = 4, history: list[dict] | None = None) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Export it in your shell profile and open a new terminal.")
    history = history or []
    client = anthropic.Anthropic()
    standalone, rewrite_usage = rewrite_query(client, question, history, model)
    results = searcher.search(standalone, books=books, articles=articles, per_doc=2)
    sources = build_sources(results)
    prompt = user_message(sources, results, question, standalone, history)
    msg = client.messages.create(model=model, max_tokens=MAX_TOKENS, system=SYSTEM, messages=[{"role": "user", "content": prompt}])
    raw = strip_headings("".join(b.text for b in msg.content if b.type == "text"))
    usage = [msg.usage.input_tokens + rewrite_usage[0], msg.usage.output_tokens + rewrite_usage[1]]
    problems = check_quotes(raw, sources)
    if problems:  # one revision pass: fix or remove the quotations that cannot be verified
        retry = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Revise your answer. These quotations cannot be verified in the passages: "
                 + "; ".join(problems) + ". Paraphrase them or quote exact continuous text from a passage (max "
                 f"{QUOTE_LIMIT_WORDS} words). Return only the revised answer."},
            ],
        )
        raw = strip_headings("".join(b.text for b in retry.content if b.type == "text"))
        usage = [usage[0] + retry.usage.input_tokens, usage[1] + retry.usage.output_tokens]
        problems = check_quotes(raw, sources)
    text, cited, suffix = link_citations(raw, sources)
    unknown = sorted({int(n) for n in re.findall(r"S(\d+)", " ".join(TAG.findall(raw)))} - {s["n"] for s in sources})
    return {
        "question": question,
        "standalone": standalone,
        "answer": text,
        "references": references_block(cited, suffix),
        "cited_docs": sorted({s["doc"]["id"] for s in cited}),
        "n_sources": len(sources),
        "retrieved_docs": [r["id"] for r in results],
        "unknown_tags": unknown,
        "usage": {"input": usage[0], "output": usage[1]},
        "stop_reason": msg.stop_reason,
        "quote_problems": problems,
        "passages_used": [
            {"cite": f"{s['cite']}", "reference": s["doc"]["reference"], "kind": s["kind"], "text": s["text"], "license": (s["doc"].get("license") or {}).get("name")} for s in cited
        ],
    }


def render(res: dict) -> str:
    foot = f"\n\n*{res['n_sources']} passages retrieved; {res['usage']['input']} input / {res['usage']['output']} output tokens.*"
    if res["quote_problems"] or res["unknown_tags"]:
        foot += f"\n\n*Check: quotation problems {res['quote_problems']}; unknown tags {res['unknown_tags']}*"
    return f"## {res['question']}\n\n{res['answer']}\n\n{res['references']}{foot}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("question", nargs="?", help="omit with --chat")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude model id (default: Haiku 4.5)")
    parser.add_argument("--chat", action="store_true", help="conversation in the terminal (empty line to quit)")
    args = parser.parse_args()
    searcher = Searcher()
    history: list[dict] = []
    try:
        while True:
            question = args.question if args.question and not history else input("\n? ").strip()
            if not question:
                break
            res = ask(question, searcher, model=args.model, history=history)
            if res["standalone"] != question:
                print(f"[searched for: {res['standalone']}]")
            print(render(res))
            history.append({"q": question, "a": res["answer"]})
            if not args.chat:
                break
    except RuntimeError as exc:
        sys.exit(str(exc))
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
