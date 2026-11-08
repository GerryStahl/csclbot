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

## How the search works

The bot must find the right passages in two very different collections: 22 long books (Gerry's own, full text) and 470 journal articles (mostly only summaries, for copyright reasons). The design follows from that: embed several kinds of semantic objects in one space, search them by meaning *and* by words, and rank books and articles separately.

### 1. Semantic objects and their embeddings

Every searchable item is turned into a 768-dimension vector by one model, `intfloat/e5-base-v2` (texts are embedded with the prefix `passage: `, questions with `query: `; vectors are normalised, so cosine similarity is a dot product). A single index must use a single model, so everything below shares it. The index holds **26,465 items** in four kinds:

| Semantic object | Items | Where the text comes from | What it is good for |
|---|---|---|---|
| **Book chunk** | 17,441 | base-level chunks (about 150 words) of the 337 chapters; vectors reused from E-Library | specific claims, arguments, definitions and examples in the books |
| **Chapter summary** | 335 | one summary per chapter (E-Library) | questions about what a whole chapter is about |
| **Article summary** | 463 | title plus a 50–60-word summary written once by Claude Haiku (Anniversary project) | topical questions about the 470 articles, whose text is not hosted |
| **Article passage** | 8,226 | 150-word windows (stride 120) of the 89 open-access articles, with exact printed pages | specific claims in articles whose licence (CC BY 4.0 / CC BY-NC 2.0) allows full text |

Larger E-Library chunk levels (section, chapter) exist in the old index but are not used: summaries cover the "whole chapter" level more cleanly, and overlapping levels would duplicate hits. Articles are matched in the semantic index at summary level (and at passage level when open access); their remaining text is reachable only through the keyword index below.

### 2. Three rankings, one fused list

For each question three rankings are computed independently (200 candidates each):

1. **Dense (semantic) ranking.** The question is embedded and compared with all 26,465 vectors. This finds passages that *mean* the same thing even when the words differ ("shared understanding" ↔ "intersubjective meaning making").
2. **Lexical ranking (BM25).** The same items are also ranked as bags of stemmed words (English stemming, stop words removed). This rewards exact terms and names that embeddings blur ("Vygotsky", "VMT", "uptake").
3. **Page-level keyword index.** A separate BM25 index of 9,276 article pages (462 articles) records which words occur on which page, with weights only. It stores **no text**, so it can cover all articles, including those whose text may not be hosted. It repairs the weakness of summaries: a rare term such as "squibs" appears in no summary but is found on the pages that use it.

**Rare-word rule.** The keyword index uses the rarest word of the question. If that word occurs in at most 60 articles it counts as *rare*: every matching article and its exact pages are listed, the two earliest matching articles are forced into the results (so "when was X first proposed?" can be answered), and the answer carries a "Search note" saying how many articles matched. For common words the keyword index only boosts the ranking and its pages are not shown.

### 3. Fusion and ranking

- **Reciprocal Rank Fusion (RRF).** An item's fused score is the sum over rankings of 1 / (60 + rank). Scores from the three rankings are not comparable, but ranks are, so no tuning of scales is needed. The keyword ranking has weight 1.5 (a hit on a rare word is strong evidence).
- **Grouping by document.** Items are grouped into documents (chapters and articles). A document's score is its best item plus 0.3 × the next two items, so a document with several good passages outranks one with a single lucky hit.
- **Books and articles ranked separately.** 17,441 book chunks would otherwise crowd out the articles. The page therefore takes the top **5 chapters** and the top **4 articles** (plus the earliest articles for rare words), with up to 2 passages per document. Each alternate version of a work (journal article ↔ book reprint) is attached to the document rather than competing with it.
- **Page attribution.** Book chunk pages are found by matching the chunk text in the volume PDFs (the old index drifts by 1–3 pages; about 1% of chunks that cannot be matched take the previous chunk's page). For articles, printed page = first page + PDF page index (469 of 470 PDFs agree with the page count).

### 4. From passages to a cited answer

The selected passages are numbered S1…Sn and given to Claude with strict rules: answer only from the passages, tag every claim `[S#]`, paraphrase summaries and keyword matches, quote only from full-text passages (at most 25 words), and decline questions outside CSCL. The program, not the model, then:

1. replaces each `[S#]` tag with an APA in-text citation and that passage's page(s), adding year suffixes (2026a, 2026b) where needed;
2. verifies every quotation against the passage text, with one revision pass, and flags any that remain unverified;
3. builds the reference list from the sources actually cited, adding every alternate version from `data/references.json` (`reprint_of`, `reprinted_in`, `originally_published_as`, `original_of`, `same_text_as`) and the licence line for open-access articles.

Follow-up questions are first rewritten into standalone questions (a short Haiku call, shown as "Searched for: …") so that the three rankings above work on a complete question; the last three turns are passed to Claude as context, but citations come only from the current turn's passages.

### 5. Why this design

- **Meaning and words.** Embeddings handle paraphrase and concepts; BM25 and the keyword index handle names, acronyms and rare terms. Each covers the other's blind spot.
- **Copyright by construction.** The hosted app holds Gerry's text, open-access article text with its licence, and for everything else only citation metadata, short summaries and a text-free keyword index.
- **Citations are data, not generation.** Because references and page numbers come from the reference data and the located pages, the model cannot invent them.

Code: `src/build_index.py` (items, vectors, BM25), `src/build_keyword_index.py` (page index), `src/search.py` (rankings, fusion, grouping), `src/answer.py` (prompt, citations, quote check, follow-up rewrite). `src/sample_results.py` writes `reports/sample_results.md` to inspect retrieval for 15 test questions.

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
az login                                  # only if the Azure sign-in has expired
bash deploy/fetch_logs.sh                 # copies the live usage.csv to data/logs/
.venv/bin/python src/usage_report.py      # summary (options: --days 30, --questions 15)
```

**Reading the report.** `src/usage_report.py` prints, for the last 30 days: the number of events (answered, blocked by a limit, errors), anonymous visitors, estimated cost, mean response time and tokens, answers with unverified quotations, and conversations (mean questions per conversation, follow-ups rewritten for search); then totals by day and by country, the most-cited documents, and the latest questions. For the full detail open `data/logs/usage.csv` in Excel: one row per event, with the question, the answer, the cited documents, the rewritten search question, tokens, cost and timing (see the columns under "Usage log" above). Country shows `unknown` when the visitor's address is not in the GeoLite2 database and `local` for this machine. The cost is an estimate from token counts; the Anthropic console shows the actual spend.

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
