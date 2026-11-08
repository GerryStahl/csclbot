# Sources and provenance

csclbot is built on three earlier projects. This repository holds only what it needs from them: metadata, short summaries and derived tables. It holds no book text and no journal-article text.

## Source projects

| Project | Repository | What csclbot uses | Commit when used |
|---|---|---|---|
| ijCSCL anniversary analysis | [GerryStahl/anniversary](https://github.com/GerryStahl/anniversary) | article records (titles, authors, volume/issue, DOI, 50–60-word Haiku summaries, codes, clusters); the trends dataset | `9eb4059` (2 Nov 2026) |
| E-Library (22 books, 337 chapters) | [GerryStahl/E-Library](https://github.com/GerryStahl/E-Library) | chapter inventory and recorded references (from `cache/elibrary_cache.json`), chunk text (from `cache/elibrary_cache.pkl`; the JSON keeps only 65-character stubs), vectors (`vector_store/*.faiss`), volume PDFs for page ranges | `5b2b38f` (28 Mar 2026) |
| Sculpture | [GerryStahl/Sculpture](https://github.com/GerryStahl/Sculpture) | not used by csclbot; listed as a related project only | – |

The three copied files below are identical to the versions in Anniversary commit `9eb4059`; their SHA-256 values identify them exactly.

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

## Keyword index of the journal articles (derived data)

Embeddings and the summaries cannot find a word that occurs only in the body of an article (for example "squibs": 26 articles contain it, one index item mentions it). `src/build_keyword_index.py` therefore builds a page-level keyword index from the local Anniversary PDFs: for each article page, only a bag of stemmed words with BM25 weights (`data/index/kw_bm25/`) and the printed page number (`kw_pages.jsonl`). It stores no text and no word order, so no text can be read back or quoted; reference lists are cut off first. Printed page = first page of the article + PDF page index (verified: 469 of 470 PDFs have exactly one PDF page per printed page; one article without a page range is skipped). 9,276 pages from 462 articles; 14 MB. The index is git-ignored and shipped in the image. Whether this kind of derived data is acceptable for Springer's articles is Gerry's decision; remove `kw_bm25/` and `kw_pages.jsonl` from `data/index/` to switch it off (the search falls back to summaries).

## Copyright policy

- Gerry holds the copyright to his own books and chapters; the deployed container image (private registry) holds their text.
- ijCSCL articles (Springer): the image holds full-text passages only for articles with a Creative Commons licence in Crossref (83 CC BY 4.0, 11 CC BY-NC 2.0; 89 have a usable PDF page range). `src/build_index.py` reads them from the local PDFs; the licence is stored in `data/references.json` (`license`) and shown with every reference that uses them. CC BY requires attribution (credit, licence link, indication of changes); CC BY-NC means the bot must stay non-commercial. For all other articles only citation metadata, short summaries and the keyword index above are stored. PDFs are never committed or shipped (`*.pdf` is git-ignored and excluded from the image build).
- Article titles come only from `metadata_corrections.csv` and `ijcscl.json`, never from PDFs.
