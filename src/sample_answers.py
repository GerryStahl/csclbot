"""Answer a fixed list of test questions with Claude and write reports/sample_answers.md.

Needs ANTHROPIC_API_KEY. Run: .venv/bin/python src/sample_answers.py
"""
from __future__ import annotations

from pathlib import Path

from answer import DEFAULT_MODEL, ask, render
from search import Searcher

OUT = Path(__file__).resolve().parent.parent / "reports" / "sample_answers.md"
QUESTIONS = [
    "How is group cognition different from individual cognition?",
    "What did the Virtual Math Teams project find about how groups do mathematics together?",
    "How can teachers be supported in orchestrating computer-supported collaborative learning?",
    "What are collaboration scripts and how do they support learner regulation?",
    "Can AI agents or chatbots take part in collaborative learning?",
    "What happens to salt marshes in Chatham as the climate changes?",
    "What is the capital of France?",
    "Summarize Gerry Stahl's view of Heidegger's influence on his work.",
]


def main() -> None:
    searcher = Searcher()
    parts = [f"# Sample answers ({DEFAULT_MODEL})", ""]
    tokens = [0, 0]
    for q in QUESTIONS:
        res = ask(q, searcher)
        tokens[0] += res["usage"]["input"]
        tokens[1] += res["usage"]["output"]
        parts += [render(res), ""]
    parts.append(f"Total: {tokens[0]} input / {tokens[1]} output tokens for {len(QUESTIONS)} questions.")
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {OUT}; tokens in/out: {tokens[0]}/{tokens[1]}")


if __name__ == "__main__":
    main()
