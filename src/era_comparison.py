"""Era comparison of the ijCSCL corpus for the 20th-anniversary paper.

Reads the research articles of 2006-2025 (src/anniversary_corpus.py: 371 articles, no editorials,
correction notices or reviews) and compares them across the four editorial eras:
  * omnibus era x label tests per coded field (chi-square statistic, permutation p-value because
    many cells are sparse, Benjamini-Hochberg q across fields) -> reports/era_comparison_tests.csv
  * label shares per era with adjusted standardized residuals -> reports/era_comparison_shares.csv
  * Figure 1: the nine labels with the largest residuals (n >= 25, excluding 'other')
    -> reports/figures/era_comparison.png / .pdf
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from anniversary_corpus import load_articles

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports"
ERAS = ["stahl_hesse_2006_2015", "ludvigsen_2016_2019", "rose_jarvela_2020_2023", "baker_reimann_2024_2027"]
ERA_TICKS = ["2006–15", "2016–19", "2020–23", "2024–25"]
FIELDS = {
    "methodology_primary": "Method",
    "unit_of_analysis_primary": "Unit of analysis",
    "pedagogy_primary": "Pedagogy",
    "technology_primary": "Technology",
    "theory_primary": "Theory",
    "ai_llm_involvement_primary": "AI/LLM",
    "category": "Category",
    "cluster_haiku_summary": "Cluster",
}
CLUSTER_NAMES = {
    "0": "collaborative knowledge building & assessment",
    "1": "teacher support & orchestration",
    "2": "collaboration scripts & learner regulation",
    "3": "online discourse & argumentation",
    "4": "CSCL field & foundations",
    "5": "embodied & immersive collaboration",
    "6": "collaborative mathematics learning",
}
# Labels whose yearly trend survived FDR correction in the Anniversary analysis
FDR_TREND = {("methodology_primary", "ethnographic_case_study"), ("cluster_haiku_summary", "1")}
PERMUTATIONS = 5000


def subset(df: pd.DataFrame, field: str) -> pd.DataFrame:
    d = df.dropna(subset=[field])
    return d[d.category.isin(list("abcdg"))] if field == "category" else d


def chi_square(era: np.ndarray, label: np.ndarray) -> float:
    table = pd.crosstab(era, label).reindex(ERAS).fillna(0).to_numpy()
    expected = table.sum(1, keepdims=True) * table.sum(0, keepdims=True) / table.sum()
    return float(((table - expected) ** 2 / np.where(expected > 0, expected, 1)).sum())


def omnibus_tests(df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for field in FIELDS:
        d = subset(df, field)
        eras, labels = d.editor_era.to_numpy(), d[field].to_numpy()
        observed = chi_square(eras, labels)
        hits = sum(chi_square(rng.permutation(eras), labels) >= observed - 1e-9 for _ in range(PERMUTATIONS))
        rows.append({"field": field, "n": len(d), "labels": d[field].nunique(), "chi2": observed, "permutation_p": (hits + 1) / (PERMUTATIONS + 1)})
    tests = pd.DataFrame(rows).sort_values("permutation_p").reset_index(drop=True)
    m = len(tests)
    q = (tests.permutation_p * m / np.arange(1, m + 1))[::-1].cummin()[::-1]
    tests["q_bh"] = q.clip(upper=1)
    return tests


def label_shares(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for field in FIELDS:
        d = subset(df, field)
        counts = pd.crosstab(d.editor_era, d[field]).reindex(ERAS).fillna(0)
        n = counts.to_numpy().sum()
        r, c = counts.sum(axis=1).to_numpy()[:, None], counts.sum(axis=0).to_numpy()[None, :]
        expected = r * c / n
        z = (counts.to_numpy() - expected) / np.sqrt(expected * (1 - r / n) * (1 - c / n))
        for j, label in enumerate(counts.columns):
            rows.append(
                {
                    "field": field,
                    "label": label,
                    "n": int(c[0, j]),
                    **{f"count_{i + 1}": int(counts.iloc[i, j]) for i in range(4)},
                    **{f"era{i + 1}_n": int(r[i, 0]) for i in range(4)},
                    "max_abs_residual": float(np.abs(z[:, j]).max()),
                }
            )
    return pd.DataFrame(rows).sort_values("max_abs_residual", ascending=False)


def wilson(k: int, n: int) -> tuple[float, float]:
    """95% Wilson interval, in percent."""
    p, z = k / n, 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return 100 * (centre - half), 100 * (centre + half)


def title_for(field: str, label: str) -> str:
    name = CLUSTER_NAMES.get(label) if field == "cluster_haiku_summary" else label.replace("_", " ")
    name = name.replace("none minimal technology", "none / minimal").replace("dyad small group", "dyad / small group")
    name = name.replace("teacher orchestrated", "teacher-orchestrated")
    return f"{FIELDS[field]}: {name}" + (" *" if (field, label) in FDR_TREND else "")


def figure(shares: pd.DataFrame) -> None:
    top = shares[(shares.n >= 25) & (shares.label != "other")].head(9)
    fig, axes = plt.subplots(3, 3, figsize=(9.5, 8.2))
    for ax, (_, row) in zip(axes.ravel(), top.iterrows()):
        ns = [row[f"era{i}_n"] for i in range(1, 5)]
        ks = [row[f"count_{i}"] for i in range(1, 5)]
        pct = [100 * k / n for k, n in zip(ks, ns)]
        ci = [wilson(k, n) for k, n in zip(ks, ns)]
        err = [[p - lo for p, (lo, _) in zip(pct, ci)], [hi - p for p, (_, hi) in zip(pct, ci)]]
        ax.bar(range(4), pct, color="#5b7fa6", width=0.65)
        ax.errorbar(range(4), pct, yerr=err, fmt="none", ecolor="#333333", capsize=3, lw=1)
        ax.set_title(title_for(row["field"], row["label"]), fontsize=8.5)
        ax.set_xticks(range(4), [f"{t}\n(n={n})" for t, n in zip(ERA_TICKS, ns)], fontsize=7)
        ax.set_ylim(0, max(hi for _, hi in ci) * 1.12)
        ax.tick_params(axis="y", labelsize=7)
        ax.set_ylabel("% of articles", fontsize=7)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.tight_layout()
    (OUT / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "figures" / "era_comparison.png", dpi=300)
    fig.savefig(OUT / "figures" / "era_comparison.pdf")


def main() -> None:
    df = load_articles()
    print(f"{len(df)} non-editorial articles, 2006-2025; per era: {df.editor_era.value_counts().reindex(ERAS).tolist()}")
    tests = omnibus_tests(df)
    shares = label_shares(df)
    tests.to_csv(OUT / "era_comparison_tests.csv", index=False)
    shares.to_csv(OUT / "era_comparison_shares.csv", index=False)
    figure(shares)
    print(tests.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
