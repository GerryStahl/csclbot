"""Run a fixed list of test questions through the search and write reports/sample_results.md.

Run: .venv/bin/python src/sample_results.py
"""
from __future__ import annotations

from pathlib import Path

from search import Searcher, format_results

OUT = Path(__file__).resolve().parent.parent / "reports" / "sample_results.md"
QUESTIONS = [
    "How is group cognition different from individual cognition?",
    "What did the Virtual Math Teams project find about how groups do mathematics together?",
    "How can collaborative dynamic geometry help students understand dependencies?",
    "What is intersubjectivity and why does it matter for collaborative learning?",
    "How did Heidegger's philosophy influence Stahl's view of interpretation and design?",
    "What are collaboration scripts and how do they support learner regulation?",
    "How can teachers be supported in orchestrating computer-supported collaborative learning?",
    "What is knowledge building and how is it assessed?",
    "How does argumentation support learning in online discussion?",
    "What is the role of interaction analysis and ethnomethodology in CSCL research?",
    "Can AI agents or chatbots take part in collaborative learning?",
    "What are the foundations and history of CSCL as a research field?",
    "What happens to salt marshes in Chatham as the climate changes?",
    "How do embodied and tabletop technologies support collaboration?",
    "What is the difference between tacit and explicit understanding in software design?",
]


def main() -> None:
    searcher = Searcher()
    parts = ["# Sample search results (retrieval only, no LLM)", "", "Per question: the 5 best book chapters and the 4 best ijCSCL articles; snippets are the best-matching passages.", ""]
    for q in QUESTIONS:
        parts.append(format_results(q, searcher.search(q)))
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {OUT} ({len(QUESTIONS)} questions)")


if __name__ == "__main__":
    main()
