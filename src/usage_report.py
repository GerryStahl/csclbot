"""Summarize data/logs/usage.csv: totals by day and country, cost, top cited documents, recent questions.

Run: .venv/bin/python src/usage_report.py [--days 30] [--questions 15]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from usage_log import LOG_FILE

REFS = Path(__file__).resolve().parent.parent / "data" / "references.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--questions", type=int, default=15)
    args = parser.parse_args()
    if not LOG_FILE.exists():
        raise SystemExit(f"No log yet at {LOG_FILE}")
    df = pd.read_csv(LOG_FILE, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
    df = df[df.timestamp_utc >= df.timestamp_utc.max() - pd.Timedelta(days=args.days)]
    for col in ("input_tokens", "output_tokens", "est_cost_usd", "seconds"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    ans = df[df.event == "answered"]

    print(f"# Usage, last {args.days} days ({df.timestamp_utc.min():%Y-%m-%d} to {df.timestamp_utc.max():%Y-%m-%d})\n")
    print(f"events: {len(df)}; answered: {len(ans)}; blocked: {(df.event == 'blocked').sum()}; errors: {(df.event == 'error').sum()}")
    print(f"visitors (anonymous ids): {df.visitor.nunique()}; estimated cost: ${ans.est_cost_usd.sum():.3f}; "
          f"mean response time: {ans.seconds.mean():.1f} s; mean tokens in/out: {ans.input_tokens.mean():.0f}/{ans.output_tokens.mean():.0f}")
    print(f"answers with unverified quotations: {(ans.quote_problems != '').sum()}")
    if "conversation" in ans.columns and (ans.conversation != "").any():
        turns = ans[ans.conversation != ""].groupby("conversation").size()
        print(f"conversations: {len(turns)}; mean questions per conversation: {turns.mean():.1f}; "
              f"follow-ups rewritten for search: {(ans.searched_for != '').sum()}")
    print()

    by_day = df.assign(day=df.timestamp_utc.dt.date).groupby("day").agg(
        events=("event", "size"), answered=("event", lambda s: (s == "answered").sum()), visitors=("visitor", "nunique"), cost_usd=("est_cost_usd", "sum"))
    print("## By day\n\n" + by_day.round(3).to_string() + "\n")
    print("## By country (answered questions)\n\n" + ans.groupby("country").agg(questions=("event", "size"), visitors=("visitor", "nunique")).sort_values("questions", ascending=False).to_string() + "\n")

    titles = {d["id"]: f"{d['cite_short']} {(d['title'] or '')[:60]}" for d in json.loads(REFS.read_text(encoding="utf-8"))["documents"]}
    cited = Counter(i for cell in ans.cited_docs for i in cell.split("; ") if i)
    print("## Most cited documents\n")
    for doc_id, n in cited.most_common(10):
        print(f"{n:>4}  {titles.get(doc_id, doc_id)}")
    print(f"\n## Latest {args.questions} questions\n")
    for _, r in ans.tail(args.questions).iterrows():
        print(f"{r.timestamp_utc:%Y-%m-%d %H:%M}  [{r.country}] {r.question[:140]}")


if __name__ == "__main__":
    main()
