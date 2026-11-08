"""The CSCL Bot: the csclbot web page (Gradio).

Search (src/search.py) -> Claude answer (with memory for follow-up questions) with APA citations (src/answer.py), with a per-visitor rate
limit and a daily spend cap (src/limits.py). Claude only; no local models.

Run: ANTHROPIC_API_KEY=... .venv/bin/python src/app.py      (http://127.0.0.1:7860)
Every event is logged to data/logs/usage.csv (src/usage_log.py); report with src/usage_report.py.
Environment: PORT, HOST (0.0.0.0 in a container), CSCLBOT_HOURLY_LIMIT, CSCLBOT_DAILY_LIMIT,
CSCLBOT_DAILY_SPEND_CAP_USD, see src/limits.py.
"""
from __future__ import annotations

import os
import secrets
import time

import anthropic
import gradio as gr

from answer import DEFAULT_MODEL, ask
from limits import Limiter, cost_usd
from usage_log import country_for, log_event, visitor_id
from search import Searcher

MAX_QUESTION_CHARS = 600
MAX_TURNS = 8  # questions per conversation
TITLE = "The CSCL Bot"
INTRO = """\
Ask a question about **computer-supported collaborative learning (CSCL)**. csclbot searches
Gerry Stahl's 22 e-library volumes and the articles of the *International Journal of
Computer-Supported Collaborative Learning* (ijCSCL, 2006–2025), then writes a short answer that cites its
sources in APA style, with page numbers.

*Book passages are quoted from the e-library. About a fifth of the ijCSCL articles are open access under Creative
Commons licences (CC BY 4.0 or CC BY-NC 2.0); csclbot uses passages from their full text, cites their exact pages
and shows the licence with the reference. For the other articles it holds only citation data, short summaries
and an index of which words occur on which pages (no article text), so they are paraphrased from their
summaries. The bot is for non-commercial research use.*
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


PROXY_HOPS = int(os.environ.get("CSCLBOT_PROXY_HOPS", "1"))  # trusted proxies in front of the app (Azure ingress = 1)


def client_ip(request: gr.Request | None) -> str:
    """Visitor address. Each proxy appends the address it saw to X-Forwarded-For, so the entry that
    the trusted proxy added is the one counted from the right; earlier entries can be forged by the visitor."""
    if request is None:
        return "127.0.0.1"
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
    if forwarded:
        return forwarded[-PROXY_HOPS] if len(forwarded) >= PROXY_HOPS else forwarded[0]
    return request.client.host if request.client else "unknown"


def passages_markdown(passages: list[dict]) -> str:
    if not passages:
        return "*No passages were cited.*"
    out = []
    for p in passages:
        label = {"article_summary": "summary of the article", "chapter_summary": "summary of the chapter", "article_pages": "pages where the search words occur"}.get(p["kind"], "passage")
        if p.get("license"):
            label += f" (open access, {p['license']})"
        out.append(f"**{p['cite']}** — {label}\n\n> {p['text']}")
    return "\n\n".join(out)


def respond(message: str, chat: list[dict], state: dict | None, request: gr.Request) -> tuple[list[dict], dict, str, str]:
    """One conversation turn. `state` holds the conversation id and the question/answer history of this
    browser session (server side); `chat` is what the page shows."""
    global searcher
    chat = list(chat or [])
    state = state or {"id": secrets.token_hex(4), "history": []}
    question = (message or "").strip()
    if not question:
        return chat, state, "", ""
    ip = client_ip(request)
    turn = len(state["history"]) + 1
    who = {
        "country": country_for(ip, dict(request.headers) if request else {}), "visitor": visitor_id(ip), "question": question,
        "conversation": state["id"], "turn": turn,
    }

    def reply(text: str, passages: str = "") -> tuple[list[dict], dict, str, str]:
        chat.extend([{"role": "user", "content": question}, {"role": "assistant", "content": text}])
        return chat, state, passages, ""

    if turn > MAX_TURNS:
        log_event(event="blocked", note="conversation too long", **who)
        return reply(f"This conversation has reached {MAX_TURNS} questions. Please start a new conversation with the button below.")
    if len(question) > MAX_QUESTION_CHARS:
        log_event(event="blocked", note="question too long", **who)
        return reply(f"Please shorten your question to {MAX_QUESTION_CHARS} characters or fewer.")
    blocked = limiter.check(ip)
    if blocked:
        log_event(event="blocked", note=blocked, **who)
        return reply(blocked)
    start = time.time()
    try:
        if searcher is None:
            searcher = Searcher()
        res = ask(question, searcher, history=state["history"])
    except anthropic.RateLimitError as exc:
        log_event(event="error", note=f"RateLimitError: {exc}"[:300], seconds=round(time.time() - start, 1), **who)
        return reply("The language model is busy right now. Please try again in a minute.")
    except (anthropic.APIError, RuntimeError) as exc:
        log_event(event="error", note=f"{type(exc).__name__}: {exc}"[:300], seconds=round(time.time() - start, 1), **who)
        return reply("Sorry, the answer service is not available right now. Please try again later.")
    limiter.record(res["usage"]["input"], res["usage"]["output"])
    text = f"{res['answer']}\n\n{res['references']}"
    if res["standalone"] != question:
        text = f"*Searched for: {res['standalone']}*\n\n{text}"
    if res["quote_problems"]:
        text += "\n\n*Note: a quotation in this answer could not be verified against the source text. Please check the source before quoting it.*"
    state["history"].append({"q": question, "a": res["answer"]})
    log_event(
        event="answered", answer=text, retrieved_docs=res["retrieved_docs"], cited_docs=res["cited_docs"], n_passages=res["n_sources"],
        model=DEFAULT_MODEL, input_tokens=res["usage"]["input"], output_tokens=res["usage"]["output"],
        est_cost_usd=round(cost_usd(res["usage"]["input"], res["usage"]["output"]), 5), seconds=round(time.time() - start, 1),
        quote_problems=res["quote_problems"], searched_for=res["standalone"] if res["standalone"] != question else "", **who,
    )
    return reply(text, passages_markdown(res["passages_used"]))


def new_conversation() -> tuple[list[dict], None, str, str]:
    return [], None, "", ""


def build_app() -> gr.Blocks:
    with gr.Blocks(title=TITLE) as demo:
        gr.Markdown(f"# {TITLE}\n\n{INTRO}")
        gr.Markdown(NOTICE)
        state = gr.State(None)
        chat = gr.Chatbot(label="Conversation", height=480, buttons=["copy"])
        question = gr.Textbox(label="Your question (follow-up questions are understood)", lines=2, max_lines=4, placeholder="e.g. How is group cognition different from individual cognition?")
        with gr.Row():
            ask_button = gr.Button("Ask", variant="primary")
            new_button = gr.Button("New conversation")
        gr.Examples(examples=[[e] for e in EXAMPLES], inputs=question, label="Examples")
        with gr.Accordion("Passages the latest answer is based on", open=False):
            passages = gr.Markdown()
        gr.Markdown(FOOTER)
        gr.on(triggers=[ask_button.click, question.submit], fn=respond, inputs=[question, chat, state], outputs=[chat, state, passages, question], api_name="ask", show_progress="full")
        new_button.click(new_conversation, outputs=[chat, state, passages, question], api_name="new")
    demo.queue(max_size=20, default_concurrency_limit=4)
    return demo


if __name__ == "__main__":
    searcher = Searcher()
    build_app().launch(server_name=os.environ.get("HOST", "127.0.0.1"), server_port=int(os.environ.get("PORT", "7860")))
