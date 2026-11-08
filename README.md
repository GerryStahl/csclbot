# The CSCL Bot (csclbot)

**Live at https://csclbot.gerrystahl.net**

The CSCL Bot answers questions about computer-supported collaborative learning (CSCL). It searches Gerry Stahl's 22 e-library volumes (337 chapters) and the *International Journal of Computer-Supported Collaborative Learning* (ijCSCL, 2006–2025), then writes a short answer with APA citations, page numbers and full references. Where the same work exists in several places (a journal article and its book-chapter reprint, or a chapter's original publication) every reference is shown, so users can pick a source they can access.

It is a research prototype. The page tells visitors that usage, questions and answers are stored.

The repository also holds the data and analyses behind Gerry Stahl's paper for the 20th anniversary of ijCSCL, "ijCSCL Through Evolving Times".

## How it works

```
question ─► search ─► numbered passages ─► Claude answer ─► APA citations ─► page
            (dense + BM25,     (S1…Sn)       (grounded, tags     (made by the program,
             one e5-base-v2                   claims [S#])        not by the model)
             index)
```

1. **One index, one model.** 17,441 e-library chunks and 335 chapter summaries (`e5-base-v2`, vectors reused from E-Library), 463 ijCSCL article summaries, and 8,226 full-text passages of the 89 open-access articles (CC BY 4.0 or CC BY-NC 2.0 licence, read from Crossref), all embedded with the same model. The other articles are indexed by title and short summary only, plus a page-level keyword index (which words occur on which page; no text) so that rare words such as "squibs" are found. Dense, BM25 and keyword rankings are fused, then grouped into book chapters and journal articles.
2. **Grounded answer.** Claude (default `claude-haiku-4-5-20251001`) answers from the numbered passages only and tags each claim `[S#]`. Summaries and keyword matches are paraphrased, never quoted; quotations from passages are checked against the passages, with one revision pass if any cannot be verified.
3. **Citations.** The program turns each tag into an APA in-text citation with the page(s) of that passage (2026a/2026b when one author has several works in a year) and appends the references of the sources actually cited, with their alternatives. Book pages are located by matching chunk text in the volume PDFs. Article citations give the article's whole page range.
4. **Follow-up questions.** The page is a conversation. A follow-up such as "How do they support regulation?" is first rewritten into a standalone question by a short Haiku call (shown as "Searched for: …"), then answered with the last three turns as context. Citations always come from the current turn's sources. The memory lives in the visitor's session on the server; a conversation is limited to 8 questions and "New conversation" clears it.
5. **Safeguards.** Per visitor 8 questions/hour and 30/day (each turn counts); a daily spend cap ($5 by default) kept on persistent storage; questions limited to 600 characters; Claude only.
6. **Usage log.** Every event is appended to `usage.csv` (Excel-readable): time, event, country, anonymous visitor id (a salted hash; the IP address is never stored), question, answer, retrieved and cited documents, tokens, estimated cost, seconds, unverified quotations, conversation id, turn number and the rewritten search question. Country comes from a local MaxMind GeoLite2 database.

## Quick start (local)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-paper.txt
export ANTHROPIC_API_KEY=...        # in your shell profile; never in the repo or on a command line you trace

.venv/bin/python src/build_index.py                  # needs ../elibrary; writes data/index/ (git-ignored)
.venv/bin/python src/search.py "How is group cognition different from individual cognition?"
.venv/bin/python src/answer.py "How can teachers be supported in orchestrating CSCL?"
.venv/bin/python src/app.py                          # http://127.0.0.1:7860
```

Test sets: `src/sample_results.py` (15 questions, retrieval only → `reports/sample_results.md`), `src/sample_answers.py` (8 questions with Claude → `reports/sample_answers.md`) and `src/sample_conversations.py` (scripted follow-up conversations → `reports/sample_conversations.md`; `src/answer.py --chat` starts a conversation in the terminal). Limits and prices can be overridden with `CSCLBOT_*` environment variables (see `src/limits.py`).

## Hosting and usage reports

The app runs on Azure Container Apps (scale to zero, one replica), built in the cloud from the [Dockerfile](Dockerfile). Deployment, resource names, DNS and update steps: [documentation/deployment.md](documentation/deployment.md). To read the cloud usage log on your machine:

```bash
bash deploy/fetch_logs.sh                 # needs `az login`; copies usage.csv to data/logs/
.venv/bin/python src/usage_report.py      # totals by day and country, cost, most-cited documents, latest questions
```

## Reference data

`data/references.json` and `reports/references.csv` hold one APA 7 reference with page numbers for every ijCSCL article and every e-library chapter, plus the original publications. Schema and decisions: [documentation/references_schema.md](documentation/references_schema.md). Rebuild with `src/fetch_crossref.py`, `src/locate_chapter_pages.py`, `src/build_references.py`.

## Paper analyses

Trend tests, the editorial-era comparison (Figure 1) and the full-text keyword scan for "ijCSCL Through Evolving Times" are documented, with every number mapped to its script, in [documentation/paper_analyses.md](documentation/paper_analyses.md). Both paper drafts are in `reports/`.

## Layout

| Path | Contents |
|---|---|
| `src/` | search, answer, web app, limits, usage log and report; reference pipeline; paper analyses |
| `data/inputs/` | small inputs copied from the Anniversary project (metadata, short summaries, trends dataset) |
| `data/references.json` | the reference data |
| `deploy/`, `Dockerfile` | Azure deployment scripts and image definition |
| `documentation/` | [sources](documentation/sources.md), [deployment](documentation/deployment.md), [paper analyses](documentation/paper_analyses.md), [reference schema](documentation/references_schema.md) |
| `reports/` | reference list, analysis tables, figures, sample results and answers, paper drafts |

Git-ignored and rebuilt or supplied locally: `data/index/` (search index), `data/raw/` (Crossref cache, chapter pages), `data/logs/` and `data/usage.json`, `data/GeoLite2-Country.mmdb` (MaxMind, free account), `.venv/`.

## Sources and copyright

Built on three earlier projects: [E-Library](https://github.com/GerryStahl/E-Library), [anniversary](https://github.com/GerryStahl/anniversary) and the related [Sculpture](https://github.com/GerryStahl/Sculpture) (not used here). [documentation/sources.md](documentation/sources.md) lists which files were taken, with commits and checksums. Gerry holds the copyright to his own books and chapters; the deployed image holds their text. ijCSCL articles (Springer) are included with full text only where they carry a Creative Commons licence (CC BY 4.0 or CC BY-NC 2.0, from Crossref): their licence is shown with each reference, and the bot is for non-commercial use. For all other articles only citation metadata, short summaries and a keyword index (no text) are stored. No PDFs are in the repository or the image (`*.pdf` is git-ignored and excluded from the build).
