#!/usr/bin/env python3
"""Publish a sanitized leaderboard score from a strategy repo. Stdlib only.

Run this from your PRIVATE strategy repo (e.g. tradegpt) once per day per
account. It is the missing link between "the strategy computed a return" and
"the public leaderboard shows it": it builds the score file the leaderboard
expects, re-checks the privacy floor locally (percentages + dates only — never
balances), then writes it to the public leaderboard's `score-update` branch via
the GitHub contents API. The leaderboard's own sync-scores workflow validates it
AGAIN server-side and renders — so a mistake here can never corrupt main.

It appends today's point to the account's existing history (fetched from the
leaderboard), so each day you only pass today's number.

Vendor this file next to scripts/validate_score.py (it imports it) — the two are
a matched pair; the leaderboard's server-side copy stays authoritative.

    GITHUB_TOKEN=<token with contents:write on the leaderboard repo> \
    python3 publish_score.py \
        --repo SevLuc/vibe-trade-leaderboard \
        --github SevLuc --name luc-theme-concentrated \
        --account paper --joined 2026-06-05 \
        --as-of 2026-07-01 --return-pct 1.75

Flags:
  --repo         owner/name of the leaderboard repo (required).
  --github       your GitHub login; becomes the "github" field (required).
  --name         strategy label shown in the table (required).
  --account      paper | live | any [a-z0-9]+ . Omit for a single-account file
                 (scores/<github>.json). With it: scores/<github>_<account>.json.
  --joined       YYYY-MM-DD you started (required).
  --as-of        YYYY-MM-DD of today's number (required).
  --return-pct   today's cumulative % since joining (required).
  --branch       target branch (default: score-update — sync-scores merges it
                 within ~6h). Use `main` to publish immediately.
  --history-json PATH  use this full history list verbatim (JSON array of
                 {"date","return_pct"}) instead of append-to-existing.
  --dry-run      build + validate + print the file; do not touch GitHub.

Token is read from --token, then $GITHUB_TOKEN, then $GH_TOKEN.
Exit: 0 published / no change, 1 validation or API error, 2 usage error.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_score import validate_score  # authoritative local mirror

API = "https://api.github.com"


def _api(method, url, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def get_existing(repo, path, branch, token):
    """Return (history, sha) for the current file on `branch`, or ([], None)."""
    url = f"{API}/repos/{repo}/contents/{path}?ref={branch}"
    status, data = _api("GET", url, token)
    if status == 404:
        return [], None
    if status != 200:
        raise SystemExit(f"error reading {path}@{branch}: HTTP {status} {data}")
    cur = json.loads(base64.b64decode(data["content"]).decode())
    hist = [{"date": str(e["date"]), "return_pct": float(e["return_pct"])}
            for e in cur.get("history", [])]
    return hist, data["sha"]


def merge_history(existing, as_of, return_pct):
    """Set today's point (replace same-date), return a date-sorted list."""
    by_date = {e["date"]: e["return_pct"] for e in existing}
    by_date[as_of] = return_pct
    return [{"date": d, "return_pct": by_date[d]} for d in sorted(by_date)]


def build_score(args, history):
    return {
        "name": args.name,
        "github": args.github,
        "return_pct": float(args.return_pct),
        "as_of": args.as_of,
        "joined": args.joined,
        "history": history,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Publish a leaderboard score.")
    p.add_argument("--repo", required=True)
    p.add_argument("--github", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--account", default="")
    p.add_argument("--joined", required=True)
    p.add_argument("--as-of", dest="as_of", required=True)
    p.add_argument("--return-pct", dest="return_pct", type=float, required=True)
    p.add_argument("--branch", default="score-update")
    p.add_argument("--history-json", dest="history_json")
    p.add_argument("--token")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if args.account and not args.account.isalnum():
        print("--account must be alphanumeric (e.g. paper, live)", file=sys.stderr)
        return 2
    stem = f"{args.github}_{args.account}" if args.account else args.github
    path = f"scores/{stem}.json"

    token = args.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token and not args.dry_run:
        print("no token: set --token, GITHUB_TOKEN, or GH_TOKEN", file=sys.stderr)
        return 2

    if args.history_json:
        raw = json.loads(Path(args.history_json).read_text())
        history = [{"date": str(e["date"]), "return_pct": float(e["return_pct"])}
                   for e in raw]
        sha = None
        if not args.dry_run:
            _, sha = get_existing(args.repo, path, args.branch, token)
    elif args.dry_run:
        history = merge_history([], args.as_of, args.return_pct)
        sha = None
    else:
        existing, sha = get_existing(args.repo, path, args.branch, token)
        history = merge_history(existing, args.as_of, args.return_pct)

    score = build_score(args, history)

    errs = validate_score(score)
    if errs:
        print("INVALID (fix before publishing):\n- " + "\n- ".join(errs),
              file=sys.stderr)
        return 1

    content = json.dumps(score, indent=2) + "\n"
    if args.dry_run:
        print(f"# would write {path} on branch {args.branch} of {args.repo}\n")
        print(content, end="")
        return 0

    body = {
        "message": f"score {args.as_of} — {stem}",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": args.branch,
    }
    if sha:
        body["sha"] = sha  # required to update an existing file
    status, data = _api("PUT", f"{API}/repos/{args.repo}/contents/{path}",
                        token, body)
    if status in (200, 201):
        commit = (data.get("commit") or {}).get("html_url", "(committed)")
        print(f"published {path} @ {args.branch}: {commit}")
        return 0
    if status == 409:
        print(f"conflict updating {path}: the file changed on {args.branch} since "
              f"we read it — re-run to pick up the new sha.", file=sys.stderr)
        return 1
    print(f"error publishing {path}: HTTP {status} {data}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
