#!/usr/bin/env python3
"""Render scores/*.json into README.md — the leaderboard table. Stdlib only.

Deterministic: sorted by return desc then name; "days" = as_of - joined (no
clock reads), so re-rendering identical scores yields identical bytes.
Malformed files are skipped with a footnote (defense in depth — the auto-merge
validator should have rejected them upstream)."""
import json
import sys
from datetime import date
from pathlib import Path


def load_scores(scores_dir):
    rows, skipped = [], []
    for p in sorted(scores_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text())
            rows.append({
                "name": str(d["name"]),
                "return_pct": float(d["return_pct"]),
                "as_of": str(d["as_of"]),
                "days": (date.fromisoformat(str(d["as_of"]))
                         - date.fromisoformat(str(d["joined"]))).days,
            })
        except Exception as e:
            skipped.append(f"`{p.name}` skipped: {e.__class__.__name__}")
    return rows, skipped


def render(rows, skipped):
    rows = sorted(rows, key=lambda r: (-r["return_pct"], r["name"]))
    lines = ["# 🏆 vibe-trade leaderboard", "",
             "| # | Strategy | Return | As of | Days |",
             "|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['name']} | {r['return_pct']:+.2f}% "
                     f"| {r['as_of']} | {r['days']} |")
    if not rows:
        lines.append("| – | *no scores yet* | – | – | – |")
    lines += ["", "*Return = cumulative % since joining, on an Alpaca **paper** "
                  "account. Honor system — audit anyone's score via this repo's "
                  "git history.*"]
    if skipped:
        lines += ["", "<sub>" + " · ".join(skipped) + "</sub>"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    rows, skipped = load_scores(root / "scores")
    (root / "README.md").write_text(render(rows, skipped))
    print(f"rendered {len(rows)} scores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
