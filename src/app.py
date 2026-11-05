"""The CSCL Bot: the csclbot web page (Gradio).

Search (src/search.py) -> Claude answer with APA citations (src/answer.py), with a per-visitor rate
limit and a daily spend cap (src/limits.py). Claude only; no local models.

Run: ANTHROPIC_API_KEY=... .venv/bin/python src/app.py      (http://127.0.0.1:7860)
Every event is logged to data/logs/usage.csv (src/usage_log.py); report with src/usage_report.py.
Environment: PORT, HOST (0.0.0.0 in a container), CSCLBOT_HOURLY_LIMIT, CSCLBOT_DAILY_LIMIT,
CSCLBOT_DAILY_SPEND_CAP_USD, see src/limits.py.
"""
from __future__ import annotations

import os
import time

import anthropic
import gradio as gr

from answer import DEFAULT_MODEL, ask
from limits import Limiter, cost_usd
from usage_log import country_for, log_event, visitor_id
from search import Searcher

MAX_QUESTION_CHARS = 600
TITLE = "The CSCL Bot"
INTRO = """\
Ask a question about **computer-supported collaborative learning (CSCL)**. csclbot searches
Gerry Stahl's 22 e-library volumes and the articles of the *International Journal of
Computer-Supported Collaborative Learning* (ijCSCL, 2006–2025), then writes a short answer that cites its
sources in APA style, with page numbers.

*Book passages are quoted from the e-library. For ijCSCL articles csclbot holds only citation data and
short summaries, so articles are paraphrased from the summary and cited by their whole page range.*
"""
EXAMPLES = [
    "How is group cognition different from individual cognition?",
    "What did the Virtual Math Teams project find about how groups do mathematics together?",
    "How can teachers be supported in orchestrating computer-supported collaborative learning?",
    "What are collaboration scripts and how do they support learner regulation?",
    "Can AI agents or chatbots take part in collaborative learning?",
    "What is the difference between tacit and explicit understanding in software design?",
]
NOTICE = """\
**CSCL Bot is a research prototype that tests this form of support for knowledge building. Usage information is \
stored, including questions and answers. The interface may change and additional references may be added over \
time. More CSCL resources are available at [https://gerrystahl.net](https://gerrystahl.net) and they can be \
searched through a local Google search at the bottom of that webpage.**
"""
FOOTER = f"""\
*Answers are written by an AI model ({DEFAULT_MODEL}) from the retrieved sources and can contain mistakes.
Check the cited sources before relying on or quoting them. Where several sources are listed for one work
(journal article and book chapter, or original publication), choose the one you can access.*
"""

limiter = Limiter()
searcher: Searcher | None = None


def client_ip(request: gr.Request | None) -> str:
    if request is None:
        return "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


def passages_markdown(passages: list[dict]) -> str:
    if not passages:
        return "*No passages were cited.*"
    out = []
    for p in passages:
        label = "summary of the article" if p["kind"] == "article_summary" else ("summary of the chapter" if p["kind"] == "chapter_summary" else "passage")
        out.append(f"**{p['cite']}** — {label}\n\n> {p['text']}")
    return "\n\n".join(out)


def respond(question: str, request: gr.Request) -> tuple[str, str]:
    global searcher
    question = (question or "").strip()
    if not question:
        return "Please type a question.", ""
    ip = client_ip(request)
    who = {"country": country_for(ip, dict(request.headers) if request else {}), "visitor": visitor_id(ip), "question": question}
    if len(question) > MAX_QUESTION_CHARS:
        log_event(event="blocked", note="question too long", **who)
        return f"Please shorten your question to {MAX_QUESTION_CHARS} characters or fewer.", ""
    blocked = limiter.check(ip)
    if blocked:
        log_event(event="blocked", note=blocked, **who)
        return blocked, ""
    start = time.time()
    try:
        if searcher is None:
            searcher = Searcher()
        res = ask(question, searcher)
    except anthropic.RateLimitError as exc:
        log_event(event="error", note=f"RateLimitError: {exc}"[:300], seconds=round(time.time() - start, 1), **who)
        return "The language model is busy right now. Please try again in a minute.", ""
    except (anthropic.APIError, RuntimeError) as exc:
        log_event(event="error", note=f"{type(exc).__name__}: {exc}"[:300], seconds=round(time.time() - start, 1), **who)
        return "Sorry, the answer service is not available right now. Please try again later.", ""
    limiter.record(res["usage"]["input"], res["usage"]["output"])
    text = f"{res['answer']}\n\n{res['references']}"
    if res["quote_problems"]:
        text += "\n\n*Note: a quotation in this answer could not be verified against the source text. Please check the source before quoting it.*"
    log_event(
        event="answered", answer=text, retrieved_docs=res["retrieved_docs"], cited_docs=res["cited_docs"], n_passages=res["n_sources"],
        model=DEFAULT_MODEL, input_tokens=res["usage"]["input"], output_tokens=res["usage"]["output"],
        est_cost_usd=round(cost_usd(res["usage"]["input"], res["usage"]["output"]), 5), seconds=round(time.time() - start, 1),
        quote_problems=res["quote_problems"], **who,
    )
    return text, passages_markdown(res["passages_used"])


def build_app() -> gr.Blocks:
    with gr.Blocks(title=TITLE) as demo:
        gr.Markdown(f"# {TITLE}\n\n{INTRO}")
        gr.Markdown(NOTICE)
        question = gr.Textbox(label="Your question", lines=2, max_lines=4, placeholder="e.g. How is group cognition different from individual cognition?")
        ask_button = gr.Button("Ask", variant="primary")
        gr.Examples(examples=[[e] for e in EXAMPLES], inputs=question, label="Examples")
        answer = gr.Markdown(label="Answer", container=True)
        with gr.Accordion("Passages the answer is based on", open=False):
            passages = gr.Markdown()
        gr.Markdown(FOOTER)
        gr.on(triggers=[ask_button.click, question.submit], fn=respond, inputs=question, outputs=[answer, passages], api_name="ask", show_progress="full")
    demo.queue(max_size=20, default_concurrency_limit=4)
    return demo


if __name__ == "__main__":
    searcher = Searcher()
    build_app().launch(server_name=os.environ.get("HOST", "127.0.0.1"), server_port=int(os.environ.get("PORT", "7860")))
