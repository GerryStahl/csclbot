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

1. **One index, one model.** 17,441 e-library chunks and 335 chapter summaries (`e5-base-v2`, vectors reused from E-Library) plus 463 ijCSCL article summaries embedded with the same model. Journal articles are indexed by title and short summary only; no article text is stored. Dense and BM25 rankings are fused, then grouped into book chapters and journal articles.
2. **Grounded answer.** Claude (default `claude-haiku-4-5-20251001`) answers from the numbered passages only and tags each claim `[S#]`. Article summaries are paraphrased, never quoted; quotations are checked against the passages, with one revision pass if any cannot be verified.
3. **Citations.** The program turns each tag into an APA in-text citation with the page(s) of that passage (2026a/2026b when one author has several works in a year) and appends the references of the sources actually cited, with their alternatives. Book pages are located by matching chunk text in the volume PDFs. Article citations give the article's whole page range.
4. **Safeguards.** Per visitor 8 questions/hour and 30/day; a daily spend cap ($5 by default) kept on persistent storage; questions limited to 600 characters; Claude only.
5. **Usage log.** Every event is appended to `usage.csv` (Excel-readable): time, event, country, anonymous visitor id (a salted hash; the IP address is never stored), question, answer, retrieved and cited documents, tokens, estimated cost, seconds, unverified quotations. Country comes from a local MaxMind GeoLite2 database.

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

Test sets: `src/sample_results.py` (15 questions, retrieval only → `reports/sample_results.md`) and `src/sample_answers.py` (8 questions with Claude → `reports/sample_answers.md`). Limits and prices can be overridden with `CSCLBOT_*` environment variables (see `src/limits.py`).

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

Built on three earlier projects: [E-Library](https://github.com/GerryStahl/E-Library), [anniversary](https://github.com/GerryStahl/anniversary) and the related [Sculpture](https://github.com/GerryStahl/Sculpture) (not used here). [documentation/sources.md](documentation/sources.md) lists which files were taken, with commits and checksums. Gerry holds the copyright to his own books and chapters; the deployed image holds their text. For journal articles (Springer) only citation metadata and short summaries are stored: no article text and no PDFs, in the repository or the image (`*.pdf` is git-ignored and excluded from the build).
