# csclbot

Public RAG question-answering interface ("Ask Gerry's Library") over Gerry Stahl's writings and the ijCSCL journal articles, intended for Azure Container Apps.

The repository also documents the analyses for Gerry Stahl's paper for the 20th anniversary of ijCSCL, "ijCSCL Through Evolving Times".

**Status:** reference data and paper analyses are done; the hosted app is not built yet.

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
- `documentation/` — [sources](documentation/sources.md), [paper analyses](documentation/paper_analyses.md), [reference schema](documentation/references_schema.md)
- `reports/` — `references.csv`, era-comparison and trend-test tables, `figures/`, and the paper draft

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-paper.txt
```

To reproduce the paper's tables and figure, see [documentation/paper_analyses.md](documentation/paper_analyses.md).
