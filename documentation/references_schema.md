# Reference data (APA 7)

[data/references.json](../data/references.json) holds one citable record per document the bot can return, so the app can print an APA reference with page numbers next to every answer. [reports/references.csv](../reports/references.csv) lists the same records in reference format for proofreading. Both are generated; edit the scripts, not the output.

## Rebuild

```bash
.venv/bin/python src/fetch_crossref.py          # Crossref cache -> data/raw/ (re-runnable)
.venv/bin/python src/locate_chapter_pages.py    # chapter page ranges from the book PDFs -> data/raw/
.venv/bin/python src/build_references.py        # -> data/references.json, reports/references.csv
```

Sources: `data/inputs/ijcscl.json` (copy from the Anniversary project), `../elibrary/cache/elibrary_cache.json` and `../elibrary/sourcepdfs/*.pdf` (read-only siblings, needed only to rebuild), and Crossref; see [sources.md](sources.md). No article text is stored.

## Structure

```json
{
  "schema_version": "1.0",
  "style": "APA 7",
  "books":     [ { "id": "elibrary:12", "title": "...", "year": 2026, "publisher": "Gerry Stahl at Lulu",
                   "url": "https://gerrystahl.net/elibrary/math", "copyright_years": [2015, 2022, 2026],
                   "original_publication": { "year": 2015, "publisher": "...", "doi": null } } ],
  "documents": [ { "id": "ijcscl:ijCSCL_4_2_1", "...": "..." } ]
}
```

A document:

| Field | Meaning |
|---|---|
| `id` | `ijcscl:<record id in ijcscl.json>`, `elibrary:<book>.<chapter>`, or `elibrary:<book>.<chapter>#original` |
| `type` | `journal_article`, `editorial`, `book_review`, `correction`, `book_chapter`, `conference_paper`, `report`, `thesis`, `web_page`, `other` |
| `in_corpus` | `true` if the bot indexes this text; `false` for original publications that are only cited |
| `authors` | `[{family, given, initials}]` or `{literal}` |
| `year`, `original_year` | `year` is the edition cited; `original_year` produces "(Original work published …)" |
| `title`, `container` | journal (volume, issue) or book (title, editors, publisher) |
| `pages` | `{first, last, display, basis}`; `basis` is `crossref`, `PDF running head`, `elibrary_pdf` or `chapter_reference` |
| `doi`, `url` | DOI as bare identifier; e-library chapters carry the volume URL |
| `apa`, `apa_md` | full reference, plain and with `*italics*` |
| `cite_short` | `Kapur & Kinzer, 2009` / `Stahl et al., 2014`; the app adds the page, e.g. `(Stahl et al., 2014, p. 241)` |
| `corpus` | keys that join to the indexes: ijCSCL record id, or `book_number` + `chapter_number` |
| `related` | `reprint_of` / `reprinted_in` (chapter ↔ ijCSCL article), `originally_published_as` / `original_of`, `same_text_as` (same chapter in two volumes) |
| `provenance` | where authors, title and pages came from |
| `review` | `{status: ok \| review, issues: [...]}` |

Chapter pages: `pages.chunk_page_offset` converts a chunk's chapter-relative `chunk_page_number` to the book page (`book page = chunk_page_number + offset`).

## Duplicates

A journal article Gerry reprinted in an e-library volume has two records: the `ijcscl:` article (journal citation, Crossref pages) and the `elibrary:` chapter (book-chapter citation, e-library pages), linked by `reprint_of` / `reprinted_in`. 43 chapters are linked (39 editorials in volume 16 plus chapters 11.10, 12.2, 12.8 and 13.5). Chapters whose original is *not* an ijCSCL article (conference papers, other journals, handbooks, theses, web pages) get an `#original` record cited from Gerry's own recorded reference.

## Decisions to check

- **Edition cited.** Chapters cite the e-library edition actually indexed: latest copyright year on the PDF's copyright page (2026 for most) and "Gerry Stahl at Lulu", with the original publication year appended. The publisher/year Gerry recorded (e.g. MIT Press 2006) are kept in `books[].original_publication`. Page numbers are those of the e-library PDF, which differ from print editions.
- **Editors.** Every chapter is cited "In G. Stahl (Ed.)". Override per book with `BOOK_EDITORS` in `build_references.py`.
- **Authors and issue data for ijCSCL** come from Crossref (the `ijcscl.json` author lists are often truncated). Titles come from `ijcscl.json`; Crossref's title replaces it only when the stored one is a truncated prefix or an author string (flagged `title_from_crossref`).
- **Conference papers** are formatted as `[Paper presentation]`; add proceedings details where a paper was published.
- Titles keep Gerry's capitalisation (APA prefers sentence case), except ALL-CAPS titles.
- The e-library volume URL is derived from the PDF file name (`9.cscl.pdf` → `/elibrary/cscl`); verify.

## Known review items

See `review.issues` / the `issues` column of the CSV. Current ones: two records in `ijcscl.json` that share one DOI (`ijCSCL_1_1_3`, `ijCSCL_1_2_6`), three editorials without Crossref authors, one title that differs from Crossref, three unparsed original references, two chapters whose end page is estimated, one chapter reference carrying the wrong DOI (11.10). Chapter 13.5 is linked to Öner's 2016 ijCSCL article by title although Gerry's recorded reference is a 2015 poster by Öner & Stahl; confirm which it is.
