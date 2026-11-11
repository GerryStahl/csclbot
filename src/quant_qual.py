"""Did the quantitative vs qualitative (socio-cognitive vs socio-cultural) divide trend, 2006-2025?

The trends dataset has no single quantitative/qualitative label, so composites are built from the existing
codes (see GROUPS) and tested like the other labels: yearly share trends (Spearman, Mann-Kendall with
Theil-Sen slope), editorial-era differences (chi-square by permutation) and Benjamini-Hochberg q-values over
the composites. Writes reports/quant_qual_trends.csv. Composites are interpretive: see the notes in the output.

Run: .venv/bin/python src/quant_qual.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from anniversary_corpus import load_articles
from trend_tests import bh

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "quant_qual_trends.csv"
ERAS = [(2006, 2015), (2016, 2019), (2020, 2023), (2024, 2025)]
PERMUTATIONS = 5000
SEED = 20260511

STATISTICAL = {"experimental_quasi_experimental", "inferential_statistics", "descriptive_statistics", "multilevel_modeling"}
COMPUTATIONAL = {"social_network_analysis", "learning_analytics", "sequence_process_mining", "computational_linguistics_nlp"}
INTERPRETIVE = {"interaction_analysis", "ethnographic_case_study", "discourse_analysis"}
SOCIO_COGNITIVE = {"socio_cognitive", "information_processing"}
SOCIO_CULTURAL = {"sociocultural", "dialogic", "activity_theory", "communities_of_practice"}

# label -> (description, function of the dataframe returning a boolean Series)
GROUPS = {
    "method: statistical/experimental (primary)": lambda d: d.methodology_primary.isin(STATISTICAL),
    "method: interpretive interaction/ethnographic/discourse (primary)": lambda d: d.methodology_primary.isin(INTERPRETIVE),
    "method: computational (primary)": lambda d: d.methodology_primary.isin(COMPUTATIONAL),
    "method: mixed methods (primary)": lambda d: d.methodology_primary == "mixed_methods",
    "method: any statistical/experimental (primary or secondary)": lambda d: has_any(d, STATISTICAL),
    "method: any interpretive (primary or secondary)": lambda d: has_any(d, INTERPRETIVE),
    "theory: socio-cognitive/information processing (primary)": lambda d: d.theory_primary.isin(SOCIO_COGNITIVE),
    "theory: socio-cultural family (primary)": lambda d: d.theory_primary.isin(SOCIO_CULTURAL),
    "unit: individual learner (primary)": lambda d: d.unit_of_analysis_primary == "individual_learner",
}


def has_any(d: pd.DataFrame, values: set[str]) -> pd.Series:
    def test(row: pd.Series) -> bool:
        found = set()
        for col in ("methodology_primary", "methodology_secondary"):
            if isinstance(row[col], str):
                found |= {v.strip() for v in row[col].split("|")}
        return bool(found & values)

    return d.apply(test, axis=1)


def era_index(year: int) -> int:
    return next(i for i, (a, b) in enumerate(ERAS) if a <= year <= b)


def era_permutation_p(flag: np.ndarray, era: np.ndarray, rng: np.random.Generator) -> float:
    def chi2(f: np.ndarray) -> float:
        table = np.array([[f[era == e].sum(), (era == e).sum() - f[era == e].sum()] for e in range(len(ERAS))], float)
        expected = table.sum(1, keepdims=True) * table.sum(0, keepdims=True) / table.sum()
        return float(((table - expected) ** 2 / expected).sum())

    observed = chi2(flag)
    hits = sum(chi2(rng.permutation(flag)) >= observed for _ in range(PERMUTATIONS))
    return (hits + 1) / (PERMUTATIONS + 1)


def main() -> None:
    d = load_articles().reset_index(drop=True)
    era = d.year.map(era_index).to_numpy()
    rng = np.random.default_rng(SEED)
    rows = []
    for label, fn in GROUPS.items():
        flag = fn(d).to_numpy().astype(int)
        yearly = pd.Series(flag).groupby(d.year).mean()
        rho, rho_p = stats.spearmanr(yearly.index, yearly.to_numpy())
        _, tau_p = stats.kendalltau(yearly.index, yearly.to_numpy())
        slope = stats.theilslopes(yearly.to_numpy() * 100, yearly.index.to_numpy())[0]
        row = {"label": label, "articles": int(flag.sum())}
        for i, (a, b) in enumerate(ERAS):
            row[f"share_{a}_{b}"] = round(100 * flag[era == i].mean(), 1)
        row.update(spearman_rho=round(rho, 2), spearman_p=round(rho_p, 3), kendall_p=round(tau_p, 3),
                   theil_sen_pp_per_year=round(slope, 2), era_permutation_p=round(era_permutation_p(flag, era, rng), 3))
        rows.append(row)
    out = pd.DataFrame(rows)
    out["kendall_q"] = bh(out.kendall_p.to_numpy()).round(3)
    out["era_q"] = bh(out.era_permutation_p.to_numpy()).round(3)
    out.to_csv(OUT, index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 70)
    print(out.to_string(index=False))
    print(f"\nN = {len(d)} research articles; wrote {OUT.relative_to(ROOT)}")
    soc = d.theory_primary.isin(SOCIO_COGNITIVE)
    stat = d.methodology_primary.isin(STATISTICAL)
    print(f"Socio-cognitive theory articles that are statistical/experimental: {int((soc & stat).sum())} of {int(soc.sum())}")
    print(f"Statistical/experimental articles with socio-cognitive theory: {int((soc & stat).sum())} of {int(stat.sum())}")


if __name__ == "__main__":
    main()
