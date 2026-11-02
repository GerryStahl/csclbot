# Sources and provenance

csclbot is built on three earlier projects. This repository holds only what it needs from them: metadata, short summaries and derived tables. It holds no book text and no journal-article text.

## Source projects

| Project | Repository | What csclbot uses | Commit when used |
|---|---|---|---|
| ijCSCL anniversary analysis | [GerryStahl/anniversary](https://github.com/GerryStahl/anniversary) | article records (titles, authors, volume/issue, DOI, 50–60-word Haiku summaries, codes, clusters); the trends dataset | `af10f5f` (24 Aug 2026) **plus uncommitted changes** (see below) |
| E-Library (22 books, 337 chapters) | [GerryStahl/E-Library](https://github.com/GerryStahl/E-Library) | chapter inventory and recorded references (from `cache/elibrary_cache.json`), volume PDFs for page ranges | `5b2b38f` (28 Mar 2026) |
| Sculpture | [GerryStahl/Sculpture](https://github.com/GerryStahl/Sculpture) | not used by csclbot; listed as a related project only | – |

The Anniversary files used here were taken from the working copy, which is ahead of the pushed commit `af10f5f`: the trends dataset (with the `src/trend_filters.py` change) and `ijcscl.json` were modified after that commit. Until those changes are pushed, the SHA-256 values below identify the exact inputs.

## Copied inputs (`data/inputs/`)

| File | Copied from | SHA-256 |
|---|---|---|
| `ijcscl.json` | `anniversary/data/processed/ijcscl.json` | `f11da401da784636b16c580e03a3588f1c3f29738be18b3f411c840a93f77055` |
| `metadata_corrections.csv` | `anniversary/data/metadata_corrections.csv` | `b6c0cc9c95be78c72d6ace7b26edd91d6011a73d04a38f43b4522a7f58386aaf` |
| `trends_dataset.csv` | `anniversary/reports/trends_dataset.csv` | `c59aa6a9a31089e97dd81d88991e7806f4e791eb148bb0e0dce5753108bee909` |

`ijcscl.json` holds no embeddings and no article text. `trends_dataset.csv` holds 376 non-editorial rows for 2006–2025, with the Haiku summary and the cluster, category and six-dimension codes.

## Other data

| Item | Source | Where |
|---|---|---|
| Page ranges, issue and full author lists for ijCSCL articles | [Crossref](https://api.crossref.org) | cached in `data/raw/crossref_ijcscl.json` (git-ignored, rebuilt by `src/fetch_crossref.py`) |
| First/last page of each e-library chapter | scan of the volume PDFs | `data/raw/elibrary_chapter_pages.json` (git-ignored, rebuilt by `src/locate_chapter_pages.py`; needs `../elibrary`) |
| APA references (output) | merged from the above | `data/references.json`, `reports/references.csv`; see [references_schema.md](references_schema.md) |

## Copyright policy

- Gerry holds the copyright to his own books and chapters.
- For ijCSCL articles the repository stores only citation metadata and short summaries. Article PDFs and text stay under `data/private/` (git-ignored) on the local machine.
- Article titles come only from `metadata_corrections.csv` and `ijcscl.json`, never from PDFs.
