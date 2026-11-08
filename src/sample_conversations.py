"""Run scripted follow-up conversations and write reports/sample_conversations.md.

Checks that follow-up questions are rewritten into standalone searches, that a change of topic is
recognised, and that citations stay tied to the current turn's sources. Needs ANTHROPIC_API_KEY.
Run: .venv/bin/python src/sample_conversations.py
"""
from __future__ import annotations

from pathlib import Path

from answer import DEFAULT_MODEL, ask
from search import Searcher

OUT = Path(__file__).resolve().parent.parent / "reports" / "sample_conversations.md"
CONVERSATIONS = {
    "Pronoun follow-ups": [
        "What are collaboration scripts?",
        "How do they support learner regulation?",
        "Are there studies that tested this experimentally?",
    ],
    "Reference to an earlier answer": [
        "How can teachers be supported in orchestrating collaborative learning?",
        "Tell me more about the first study you mentioned.",
    ],
    "Topic switch": [
        "What is intersubjectivity?",
        "What happens to salt marshes in Chatham as the climate changes?",
    ],
    "Rare word then follow-up": [
        "When were squibs proposed in ijCSCL?",
        "Who wrote the first one?",
    ],
}


def main() -> None:
    searcher = Searcher()
    parts = [f"# Sample conversations ({DEFAULT_MODEL})", ""]
    total = [0, 0]
    for title, questions in CONVERSATIONS.items():
        parts += [f"## {title}", ""]
        history: list[dict] = []
        for n, q in enumerate(questions, 1):
            res = ask(q, searcher, history=history)
            total[0] += res["usage"]["input"]
            total[1] += res["usage"]["output"]
            parts += [f"**Turn {n}: {q}**", ""]
            if res["standalone"] != q:
                parts += [f"*Searched for: {res['standalone']}*", ""]
            parts += [res["answer"], "", res["references"], ""]
            if res["quote_problems"]:
                parts += [f"*Check: {res['quote_problems']}*", ""]
            history.append({"q": q, "a": res["answer"]})
    parts.append(f"Total: {total[0]} input / {total[1]} output tokens.")
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {OUT}; tokens in/out: {total[0]}/{total[1]}")


if __name__ == "__main__":
    main()
