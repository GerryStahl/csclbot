"""Count context terms (pandemic, climate, social media, generative AI) in the full text of the ijCSCL research articles.

Full text is read from ../anniversary/data/processed/ijcscl.pkl (local only, never copied into this
repo). Only counts are written: reports/fulltext_keyword_scan.csv (one row per article) and a
summary printed to the console. Reference lists are cut off before counting, so cited titles do not
inflate the counts; the cut-off is reported per article.

Run with the csclbot venv: .venv/bin/python src/keyword_scan.py
"""
from __future__ import annotations

import pickle
import re
import sys
from pathlib import Path

import pandas as pd

from anniversary_corpus import load_articles

ROOT = Path(__file__).resolve().parent.parent
PKL = ROOT.parent / "anniversary" / "data" / "processed" / "ijcscl.pkl"
OUT = ROOT / "reports" / "fulltext_keyword_scan.csv"

TERMS = {
    "pandemic": r"covid|coronavirus|sars-cov|pandemic|emergency remote",
    # strict: the climate crisis itself; broad adds sustainability and environmental-issue wording
    "climate_strict": r"climate change|climate crisis|climate emergency|global warming|climate action|climate literacy",
    "sustainability": r"sustainable development|environmental (?:sustainab\w*|crisis|crises|issues?|problems?|education|protection|challenges?)|ecological (?:crisis|crises|sustainab\w*|transition)",
    "social_media": r"social media\b|facebook|twitter|instagram|tiktok|whatsapp|snapchat|reddit",
    "generative_ai": r"generative ai|chatgpt|large language models?|\bllms?\b|gpt-?[34]|gen-?ai",
}
REFERENCES = re.compile(r"^\W*(?:references|reference list|bibliography)\W*$", re.I | re.M)


class _Stub:
    """Stand-in for the Anniversary project's Article class, so its code is not needed."""

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)


class _Unpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        return _Stub if module.startswith("src.") else super().find_class(module, name)


def body_text(text: str) -> tuple[str, bool]:
    """Text before the last 'References' heading (searched in the second half only)."""
    cuts = [m.start() for m in REFERENCES.finditer(text) if m.start() > len(text) * 0.4]
    return (text[: cuts[-1]], True) if cuts else (text, False)


def show_contexts(store: dict, have: pd.DataFrame, per_term: int = 8) -> None:
    """Console only: a few 12-word snippets per term to check that hits mean what we think (not saved)."""
    for name in ("pandemic", "climate_strict", "sustainability", "social_media"):
        print(f"\n--- {name} ---")
        hits = have[have[name] > 0].sort_values(name, ascending=False).head(per_term)
        for _, r in hits.iterrows():
            body, _ = body_text(getattr(store[r["id"]], "fulltext", "") or "")
            m = re.search(TERMS[name], body, re.I)
            words = body[max(0, m.start() - 70) : m.end() + 70].split()
            print(f"{r['year']} [{r[name]}x] ...{' '.join(words[1:-1])}...")


def main() -> None:
    with PKL.open("rb") as f:
        store = _Unpickler(f).load()
    articles = load_articles()
    rows = []
    for _, a in articles.iterrows():
        rec = store.get(a["id"])
        text = (getattr(rec, "fulltext", None) or getattr(rec, "text", None) or "") if rec else ""
        body, cut = body_text(text)
        row = {"id": a["id"], "year": int(a["year"]), "title": a["title"], "chars": len(text), "references_cut": cut}
        for name, pattern in TERMS.items():
            row[name] = len(re.findall(pattern, body, re.I))
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)

    have = df[df.chars > 2000]
    print(f"{len(df)} research articles; {len(have)} with usable full text (> 2,000 characters); "
          f"reference list cut in {int(have.references_cut.sum())}")
    print(f"missing/short full text: {len(df) - len(have)}")
    for name in TERMS:
        hit = have[have[name] > 0]
        print(f"\n{name}: {len(hit)} articles mention it ({len(hit) / len(have):.0%}); "
              f"{int((have[name] >= 3).sum())} mention it 3+ times, {int((have[name] >= 10).sum())} 10+ times; "
              f"{int(have[name].sum())} mentions in all")
        print("  by year (articles with a mention):", hit.groupby("year").size().to_dict())
    per_year = have.groupby("year").size()
    print("\narticles per year:", per_year.to_dict())
    print("articles 2020-2022:", int(per_year.loc[2020:2022].sum()), "| 2020-2025:", int(per_year.loc[2020:2025].sum()))
    for name in ("pandemic", "generative_ai"):
        print(f"{name}: articles with 10+ mentions:", have[have[name] >= 10][["year", "title"]].assign(title=lambda d: d.title.str[:70]).values.tolist())
    if "--contexts" in sys.argv:
        show_contexts(store, have)


if __name__ == "__main__":
    main()
