"""The ijCSCL research articles of 2006-2025 used in the anniversary paper.

Reads data/inputs/trends_dataset.csv (a copy of ../anniversary/reports/trends_dataset.csv, see
documentation/sources.md). The Anniversary pipeline's
non-editorial set (376 rows, 2006-2025) still contains correction notices and one book review;
those are dropped here, leaving the research articles.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "inputs" / "trends_dataset.csv"
NOTICE = re.compile(r"^(?:Correction|Erratum)\b|^A review of the International Handbook", re.I)


def load_articles(include_notices: bool = False) -> pd.DataFrame:
    df = pd.read_csv(DATA, dtype={"category": str, "cluster_haiku_summary": str})
    df["cluster_haiku_summary"] = df["cluster_haiku_summary"].str.replace(r"\.0$", "", regex=True)
    df = df[(df.is_editorial == "no") & (df.year <= 2025)]
    return df if include_notices else df[~df.title.str.contains(NOTICE)]
