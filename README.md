# csclbot

Public RAG question-answering interface ("The CSCL Bot") over Gerry Stahl's writings and the ijCSCL journal articles, intended for Azure Container Apps.

The repository also documents the analyses for Gerry Stahl's paper for the 20th anniversary of ijCSCL, "ijCSCL Through Evolving Times".

**Status:** reference data, paper analyses, the search index and retrieval with APA references are done ([sample results](reports/sample_results.md)); the Claude answer layer works from the command line ([sample answers](reports/sample_answers.md)); the Gradio page works locally (`src/app.py`); **live at https://csclbot.gerrystahl.net** (Azure Container Apps; see the [deployment record](documentation/deployment.md)).

## Source projects (read-only archives)

- [E-Library](https://github.com/GerryStahl/E-Library) (`../elibrary`) — 22 books / 337 chapters; FAISS + BM25 over 36,089 chunks, `e5-base-v2` (768-dim).
- [anniversary](https://github.com/GerryStahl/anniversary) (`../anniversary`) — ~470 ijCSCL articles (2006–2025); article-level data only (no chunks, no FAISS), `all-MiniLM-L6-v2` (384-dim). Hand-corrected titles live in `data/inputs/metadata_corrections.csv`.
- [Sculpture](https://github.com/GerryStahl/Sculpture) — related project of Gerry's, not used here.

See [documentation/sources.md](documentation/sources.md) for exactly which files were taken from them, with commits and checksums. This repository holds no book or journal-article text; the copyright policy is stated there.

## Layout

- `data/inputs/` — small inputs copied from the Anniversary project (metadata, short summaries, trends dataset)
- `data/references.json` — one APA reference with page numbers per citable document; [schema](documentation/references_schema.md)
- `data/` — `data/private/` and `data/raw/` are git-ignored
- `src/` — reference pipeline, paper analyses, and (later) the hosted app
- `Dockerfile`, `deploy/` — Azure Container Apps deployment (`deploy.sh`, `containerapp.yaml`, `fetch_logs.sh`)
- `documentation/` — [sources](documentation/sources.md), [paper analyses](documentation/paper_analyses.md), [reference schema](documentation/references_schema.md)
- `reports/` — `references.csv`, era-comparison and trend-test tables, `figures/`, and the paper draft

## Search (retrieval only)

One index, one embedding model (`e5-base-v2`, 768-dim): 17,441 e-library chunks and 335 chapter summaries (vectors reused from E-Library) plus 463 ijCSCL article summaries (embedded here; no article text). Dense and BM25 rankings are fused, then grouped into book chapters and journal articles. Every result carries its APA reference, an in-text citation with page(s), and the linked references (journal article ↔ book-chapter reprint, original publication), so users can choose a source they can access.

```bash
.venv/bin/python src/build_index.py                       # needs ../elibrary; writes data/index/ (git-ignored)
.venv/bin/python src/search.py "How is group cognition different from individual cognition?"
.venv/bin/python src/sample_results.py                    # 15 test questions -> reports/sample_results.md
```

Book pages are located by matching each chunk's text in the volume PDF (the page numbers in the old index drift by 1–3 pages). About 1% of chunks could not be matched and take the previous chunk's page. Article citations give the whole article's page range, because articles are indexed by summary only.

## Answers (Claude)

`src/answer.py` retrieves the best passages (up to two per document), numbers them S1…Sn, and asks Claude (default `claude-haiku-4-5-20251001`) to answer from those sources only, tagging claims with `[S#]`. The program, not the model, turns each tag into an APA in-text citation with the page(s) of that passage (2026a/2026b when one author has several works in a year) and appends the full references of the sources actually cited, with their alternative sources. Journal articles are represented by short summaries only, so they are paraphrased, never quoted. Quotations are checked against the passages; one revision pass runs if any cannot be verified, and anything still unverified is flagged.

```bash
export ANTHROPIC_API_KEY=...      # in your shell profile, never in the repo
.venv/bin/python src/answer.py "How is group cognition different from individual cognition?" [--model MODEL]
.venv/bin/python src/sample_answers.py                     # 8 test questions -> reports/sample_answers.md
```

Cost with Haiku is roughly 4,000 input and 450 output tokens per question (check current Anthropic pricing).

## Web page

```bash
.venv/bin/python src/app.py        # http://127.0.0.1:7860 (set PORT to change); needs ANTHROPIC_API_KEY
```

`src/app.py` is a Gradio page (question box, examples, answer with references, a collapsible panel of the passages used). Claude only. `src/limits.py` limits each visitor to 8 questions per hour and 30 per day and stops answering when the day's estimated spend reaches the cap ($5 by default); the spend total is kept in `data/usage.json` (git-ignored). Override with `CSCLBOT_HOURLY_LIMIT`, `CSCLBOT_DAILY_LIMIT`, `CSCLBOT_DAILY_SPEND_CAP_USD`, and the per-million-token prices with `CSCLBOT_INPUT_USD_PER_MTOK` and `CSCLBOT_OUTPUT_USD_PER_MTOK` (defaults are for Haiku 4.5; check Anthropic's current prices).

**Usage log.** Every event (answered, blocked, error) is appended to `data/logs/usage.csv` (git-ignored; open it in Excel): time, event, country, anonymous visitor id, question, answer, retrieved and cited documents, passages, model, tokens, estimated cost, seconds, unverified quotations. The IP address is never stored: the visitor id is a salted hash. Country comes from a CDN header (`CF-IPCountry`) or from a local MaxMind GeoLite2 Country database (free account needed; save it as `data/GeoLite2-Country.mmdb` or set `CSCLBOT_GEOIP_DB`); otherwise it is `unknown`, and `local` for this machine. The page tells visitors that questions and answers are stored. In the cloud set `CSCLBOT_LOG_DIR` to a persistent volume. Summarize with `.venv/bin/python src/usage_report.py` (totals by day and country, cost, most-cited documents, latest questions). Questions are not logged.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-paper.txt
```

To reproduce the paper's tables and figure, see [documentation/paper_analyses.md](documentation/paper_analyses.md).
