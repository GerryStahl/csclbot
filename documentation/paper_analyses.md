# Analyses behind "ijCSCL Through Evolving Times"

This page documents how each number in the 20th-anniversary paper ([draft](../reports/ijCSCL%20Through%20Evolving%20Times%20(draft%202).docx)) was produced. The article-level coding itself (summaries, embeddings, clusters, categories, six-dimension codes) was done in the [Anniversary project](https://github.com/GerryStahl/anniversary); csclbot re-runs the statistics on the corrected set of articles.

## Article set

| Count | Meaning |
|---|---|
| 458 | items published in ijCSCL 2006–2025 (editorials, notices and research articles) |
| 376 | non-editorial items in `data/inputs/trends_dataset.csv` (the Anniversary pipeline's set) |
| **371** | research articles analyzed: the 376 minus four correction notices and one book review (`src/anniversary_corpus.py`) |

Within the 371, the categories "editorial" (e) and "none of the above" (f) do not occur, so five category codes (a, b, c, d, g) were tested. The 69 tested labels are 7 semantic clusters, 5 categories and 57 values of the six coded dimensions.

## Steps

| Step | Done by | Output |
|---|---|---|
| Summaries (Claude Haiku 4.5), embeddings (all-MiniLM-L6-v2), K-means clusters (k = 7), categories, six-dimension coding | Anniversary project | `data/inputs/trends_dataset.csv` |
| Yearly trend tests: linear regression of yearly counts and of yearly shares, Mann–Kendall with Theil–Sen slope on shares, each with Benjamini–Hochberg FDR over 69 labels; embedding drift of the yearly centroid | `src/trend_tests.py` | `reports/trend_tests.csv` |
| Era comparison across the four editorial eras: chi-square statistic with a 5,000-permutation p-value for each coded field, BH q over the 8 fields; label shares with adjusted standardized residuals; Figure 1 | `src/era_comparison.py` | `reports/era_comparison_tests.csv`, `reports/era_comparison_shares.csv`, `reports/figures/era_comparison.png` and `.pdf` |
| APA reference data | `src/fetch_crossref.py`, `src/locate_chapter_pages.py`, `src/build_references.py` | `data/references.json`, `reports/references.csv` |

Eras: Stahl and Hesse 2006–2015 (194 articles), Ludvigsen 2016–2019 (69), Rosé and Järvelä 2020–2023 (76), Baker and Reimann 2024–2025 (32).

## Results as used in the paper

- Only two of the 69 yearly trends survive FDR correction: ethnographic case studies decline (q = .022 for the regression on counts, .022 on shares, .047 in Mann–Kendall) and the teacher-support-and-orchestration cluster (cluster 1, 87 articles) rises (q = .018 on shares, .022 in Mann–Kendall; the regression on counts gives .075).
- No category (design of collaboration, design of technology, analysis of interaction, measurement of learning, CSCL theory) shows a significant trend.
- Era differences are largest for pedagogy, method and semantic cluster (permutation p = .023, .036, .041), but q = .11 for all three after correction over the eight fields. They are described as suggestive.
- Of the 54 articles of 2023–2025, 6 carry an AI label and 2 are about generative AI.

## Cluster labels

The cluster numbers are arbitrary K-means ids; the names were interpreted by Gerry from titles and summaries: 0 collaborative knowledge building and assessment; 1 teacher support and orchestration; 2 collaboration scripts and learner regulation; 3 online discourse and argumentation; 4 CSCL field and foundations; 5 embodied and immersive collaboration; 6 collaborative mathematics learning.

## Limits

One LLM did all of the coding, with no human validation (a validation sample is a recommended next step). Each article is represented by a 50–60-word summary. The yearly series are short (20 points) and the last era has only 32 articles.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-paper.txt
.venv/bin/python src/trend_tests.py         # also prints the embedding drift
.venv/bin/python src/era_comparison.py      # tables and Figure 1
```

Both scripts read only `data/inputs/`. Pass `--include-notices` to `trend_tests.py` to reproduce the original 376-row analysis for comparison. The reference pipeline needs the sibling `../elibrary` project and network access for Crossref; its output is committed.
