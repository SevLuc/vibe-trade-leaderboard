#!/usr/bin/env python3
"""Render scores/*.json into README.md + chart.svg + sparklines/*.svg. Stdlib only.

Deterministic (no clock reads, fixed coordinates): re-rendering identical scores
yields identical bytes. "days" = as_of - joined. Malformed score files are
skipped with a footnote (defense in depth — the auto-merge validator should have
rejected them upstream). Only percentages and dates are ever drawn — never any
dollar amount (the privacy floor).

Generated artifacts, all committed so the README's <img> tags resolve:
- chart.svg          — cumulative-return lines, one per participant (≥1 score).
- sparklines/<gh>.svg — a tiny per-participant trend, embedded in the table.
"""
import json
import sys
from datetime import date
from pathlib import Path

# Stable per-person line colours (assigned by sorted github login, so a given
# player keeps their colour regardless of daily rank). Saturated mid-tones that
# read on both light and dark README backgrounds.
_PALETTE = ["#185FA5", "#0F6E56", "#D85A30", "#534AB7", "#993556",
            "#854F0B", "#0C447C", "#A32D2D"]
_POS, _NEG, _AXIS, _ZERO = "#1a7f37", "#cf222e", "#888888", "#999999"


def load_scores(scores_dir):
    rows, skipped = [], []
    for p in sorted(scores_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text())
            hist = [{"date": str(e["date"]), "return_pct": float(e["return_pct"])}
                    for e in d["history"]]
            rows.append({
                "name": str(d["name"]),
                "github": str(d["github"]),
                "return_pct": float(d["return_pct"]),
                "as_of": str(d["as_of"]),
                "days": (date.fromisoformat(str(d["as_of"]))
                         - date.fromisoformat(str(d["joined"]))).days,
                "history": hist,
            })
        except Exception as e:
            skipped.append(f"`{p.name}` skipped: {e.__class__.__name__}")
    return rows, skipped


def _n(v):
    """Stable 1-dp coordinate string (avoids float artifacts in committed SVG)."""
    return f"{v:.1f}"


def sparkline_svg(history):
    """An 80x20 trend line for one participant; green/red by latest sign."""
    pts = [h["return_pct"] for h in history]
    colour = _NEG if pts and pts[-1] < 0 else _POS
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    n = len(pts)
    def x(i):
        return 2.0 if n == 1 else 2.0 + i * (76.0 / (n - 1))
    def y(v):
        return 18.0 - (v - lo) / span * 16.0   # 18 (bottom) .. 2 (top)
    body = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 20" '
            f'width="80" height="20" role="img" aria-label="trend">']
    if n == 1:
        body.append(f'<circle cx="40" cy="10" r="2.2" fill="{colour}"/>')
    else:
        coords = " ".join(f"{_n(x(i))},{_n(y(v))}" for i, v in enumerate(pts))
        body.append(f'<polyline points="{coords}" fill="none" stroke="{colour}" '
                    f'stroke-width="1.5"/>')
        body.append(f'<circle cx="{_n(x(n-1))}" cy="{_n(y(pts[-1]))}" r="1.8" '
                    f'fill="{colour}"/>')
    body.append("</svg>")
    return "".join(body) + "\n"


def chart_svg(rows):
    """Cumulative-return lines for all participants over their shared dates."""
    W, H = 640, 260
    L, R, T, B = 44, 140, 16, 28
    pw, ph = W - L - R, H - T - B
    dates = sorted({h["date"] for r in rows for h in r["history"]})
    dx = {d: i for i, d in enumerate(dates)}
    vals = [h["return_pct"] for r in rows for h in r["history"]] + [0.0]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1.0
    lo, hi = lo - pad, hi + pad
    span = hi - lo

    def px(i):
        return L if len(dates) <= 1 else L + i * (pw / (len(dates) - 1))

    def py(v):
        return T + (hi - v) / span * ph

    colour = {r["github"]: _PALETTE[i % len(_PALETTE)]
              for i, r in enumerate(sorted(rows, key=lambda r: r["github"]))}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'width="{W}" height="{H}" role="img" '
           f'aria-label="Cumulative percent return since joining, per strategy">']
    # zero baseline
    yz = py(0.0)
    out.append(f'<line id="zero" x1="{L}" y1="{_n(yz)}" x2="{L+pw}" y2="{_n(yz)}" '
               f'stroke="{_ZERO}" stroke-width="1" stroke-dasharray="3 3"/>')
    out.append(f'<text x="{L-6}" y="{_n(yz+3)}" font-size="10" fill="{_AXIS}" '
               f'text-anchor="end" font-family="sans-serif">0%</text>')
    # y extremes
    out.append(f'<text x="{L-6}" y="{_n(T+8)}" font-size="10" fill="{_AXIS}" '
               f'text-anchor="end" font-family="sans-serif">{hi:+.1f}%</text>')
    out.append(f'<text x="{L-6}" y="{_n(T+ph)}" font-size="10" fill="{_AXIS}" '
               f'text-anchor="end" font-family="sans-serif">{lo:+.1f}%</text>')
    # x extremes
    out.append(f'<text x="{L}" y="{H-10}" font-size="10" fill="{_AXIS}" '
               f'font-family="sans-serif">{dates[0]}</text>')
    if len(dates) > 1:
        out.append(f'<text x="{L+pw}" y="{H-10}" font-size="10" fill="{_AXIS}" '
                   f'text-anchor="end" font-family="sans-serif">{dates[-1]}</text>')
    # one line per participant (stable colour; legend ranked by latest return)
    for r in sorted(rows, key=lambda r: (-r["return_pct"], r["name"])):
        c = colour[r["github"]]
        pts = [(px(dx[h["date"]]), py(h["return_pct"])) for h in r["history"]]
        if len(pts) == 1:
            out.append(f'<circle cx="{_n(pts[0][0])}" cy="{_n(pts[0][1])}" r="2.4" '
                       f'fill="{c}"/>')
        else:
            coords = " ".join(f"{_n(x)},{_n(y)}" for x, y in pts)
            out.append(f'<polyline points="{coords}" fill="none" stroke="{c}" '
                       f'stroke-width="2"/>')
    # legend
    ly = T + 4
    for r in sorted(rows, key=lambda r: (-r["return_pct"], r["name"])):
        c = colour[r["github"]]
        label = (r["name"][:18] + "…") if len(r["name"]) > 19 else r["name"]
        out.append(f'<line x1="{L+pw+10}" y1="{ly}" x2="{L+pw+26}" y2="{ly}" '
                   f'stroke="{c}" stroke-width="2"/>')
        out.append(f'<text x="{L+pw+30}" y="{ly+3}" font-size="10" fill="{_AXIS}" '
                   f'font-family="sans-serif">{label} {r["return_pct"]:+.1f}%</text>')
        ly += 16
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render(rows, skipped):
    rows = sorted(rows, key=lambda r: (-r["return_pct"], r["name"]))
    lines = ["# 🏆 vibe-trade leaderboard", ""]
    if rows:
        lines += ["![cumulative return since joining](chart.svg)", ""]
    lines += ["| # | Strategy | Return | Trend | As of | Days |",
              "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        spark = (f'<img src="sparklines/{r["github"]}.svg" alt="trend" '
                 f'height="20">')
        lines.append(f"| {i} | {r['name']} | {r['return_pct']:+.2f}% | {spark} "
                     f"| {r['as_of']} | {r['days']} |")
    if not rows:
        lines.append("| – | *no scores yet* | – | – | – | – |")
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
    if rows:
        (root / "chart.svg").write_text(chart_svg(rows))
        spark_dir = root / "sparklines"
        spark_dir.mkdir(exist_ok=True)
        for r in rows:
            (spark_dir / f"{r['github']}.svg").write_text(sparkline_svg(r["history"]))
    print(f"rendered {len(rows)} scores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
