"""Yearly trend tests for the ijCSCL research articles, 2006-2025 (anniversary paper).

Re-runs, on the corrected article set (src/anniversary_corpus.py), the three yearly-trend tests of
the Anniversary pipeline: linear regression on yearly counts, linear regression on yearly shares,
and Mann-Kendall / Theil-Sen on yearly shares, each with Benjamini-Hochberg FDR control across all
labels. Also recomputes the embedding drift of the yearly centroid of the Haiku summaries
(all-MiniLM-L6-v2) from the 2006 centroid. Output: reports/trend_tests.csv.

Use --include-notices to reproduce the original 376-row analysis for comparison.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats

from anniversary_corpus import load_articles
from era_comparison import FIELDS, OUT

YEARS = list(range(2006, 2026))
CATEGORY_CODES = list("abcdg")


def bh(p: np.ndarray) -> np.ndarray:
    order = np.argsort(p)
    ranked = p[order] * len(p) / np.arange(1, len(p) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1].clip(max=1)
    out = np.empty_like(q)
    out[order] = q
    return out


def label_series(df: pd.DataFrame) -> list[tuple[str, str, np.ndarray, np.ndarray]]:
    totals = df.groupby("year").size().reindex(YEARS, fill_value=0).to_numpy()
    series = []
    for field in FIELDS:
        d = df[df.category.isin(CATEGORY_CODES)] if field == "category" else df
        for label in sorted(d[field].dropna().unique()):
            counts = d[d[field] == label].groupby("year").size().reindex(YEARS, fill_value=0).to_numpy()
            series.append((field, label, counts, counts / totals))
    return series


def trend_tests(df: pd.DataFrame) -> pd.DataFrame:
    x = np.arange(len(YEARS))
    rows = []
    for field, label, counts, shares in label_series(df):
        lc, ls = stats.linregress(x, counts), stats.linregress(x, shares)
        kt = stats.kendalltau(x, shares)
        rows.append(
            {
                "field": field,
                "label": label,
                "total": int(counts.sum()),
                "count_slope": lc.slope,
                "count_p": lc.pvalue,
                "share_slope": ls.slope,
                "share_p": ls.pvalue,
                "kendall_tau": kt.statistic,
                "kendall_p": kt.pvalue,
                "theil_sen_slope": stats.theilslopes(shares, x)[0],
            }
        )
    out = pd.DataFrame(rows).fillna({"count_p": 1.0, "share_p": 1.0, "kendall_p": 1.0})
    for col in ("count", "share", "kendall"):
        out[f"{col}_q"] = bh(out[f"{col}_p"].to_numpy())
    return out


def embedding_drift(df: pd.DataFrame) -> pd.Series:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    emb = model.encode(df.summary_haiku.tolist(), normalize_embeddings=True)
    centroids = {y: emb[(df.year == y).to_numpy()].mean(axis=0) for y in YEARS}
    base = centroids[2006]
    cos = lambda a, b: float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    return pd.Series({y: 1 - cos(c, base) for y, c in centroids.items()})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-notices", action="store_true")
    args = parser.parse_args()
    df = load_articles(include_notices=args.include_notices)
    tests = trend_tests(df)
    print(f"{len(df)} articles, {len(tests)} labels")
    keep = tests[(tests[["count_q", "share_q", "kendall_q"]] < 0.05).any(axis=1)]
    print(keep.round(4).to_string(index=False))
    if not args.include_notices:
        tests.to_csv(OUT / "trend_tests.csv", index=False)
    drift = embedding_drift(df)
    print("distance of yearly centroid from 2006:", drift.round(3).to_dict())


if __name__ == "__main__":
    main()
