#!/usr/bin/env python3
"""Standalone leaderboard score validator — vendored, stdlib only.

A self-contained copy of the engine's canonical validator, so the auto-merge
Action can validate a score WITHOUT installing the (private) engine or holding
any read token. The engine's own test suite asserts this copy stays in lockstep
with the canonical one (drift guard). Percentages and dates only — a score must
never carry account state (the privacy floor).

CLI: `python3 validate_score.py validate <score.json>` -> OK/0, INVALID/1, usage/2.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HISTORY_CAP = 365
RETURN_BOUNDS = (-100.0, 10000.0)
_SCORE_KEYS = {"name", "github", "return_pct", "as_of", "joined", "history"}
_ENTRY_KEYS = {"date", "return_pct"}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")
_GITHUB_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_FORBIDDEN_KEY_RE = re.compile(r"equity|cash|balance|dollar|usd|amount|position", re.I)


def _is_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def _is_return(v):
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and RETURN_BOUNDS[0] <= v <= RETURN_BOUNDS[1])


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def validate_score(data):
    """Return a list of problems; empty == valid. The account-state key scan runs
    FIRST so a privacy breach is named as such, not as a generic key mismatch."""
    if not isinstance(data, dict):
        return ["score must be a JSON object"]
    errs = [f"forbidden account-state key: {k!r}"
            for k in _walk_keys(data) if _FORBIDDEN_KEY_RE.search(k)]
    if set(data) != _SCORE_KEYS:
        errs.append(f"keys must be exactly {sorted(_SCORE_KEYS)}, got {sorted(data)}")
        return errs
    if not (isinstance(data["name"], str) and _NAME_RE.match(data["name"])):
        errs.append("name must be a short label (letters/digits/space/_/./-, max 40)")
    if not (isinstance(data["github"], str) and _GITHUB_RE.match(data["github"])):
        errs.append("github must be a valid GitHub username (1-39 chars, alphanumeric/hyphen)")
    if not _is_return(data["return_pct"]):
        errs.append(f"return_pct must be a number in {RETURN_BOUNDS}")
    for k in ("as_of", "joined"):
        if not _is_date(data[k]):
            errs.append(f"{k} must be a YYYY-MM-DD date")
    if _is_date(data["as_of"]) and _is_date(data["joined"]) and data["joined"] > data["as_of"]:
        errs.append("joined must not be after as_of")
    h = data["history"]
    if not isinstance(h, list) or len(h) > HISTORY_CAP:
        errs.append(f"history must be a list of at most {HISTORY_CAP} entries")
    else:
        bad = [e for e in h
               if not (isinstance(e, dict) and set(e) == _ENTRY_KEYS
                       and _is_date(e["date"]) and _is_return(e["return_pct"]))]
        if bad:
            errs.append(f"{len(bad)} bad history entries, first: {bad[0]!r}")
    return errs


def _cli(argv):
    if len(argv) != 2 or argv[0] != "validate":
        print("usage: python3 validate_score.py validate <score.json>", file=sys.stderr)
        return 2
    try:
        data = json.loads(Path(argv[1]).read_text())
    except (OSError, ValueError) as e:
        print(f"INVALID: unreadable JSON ({e})")
        return 1
    errs = validate_score(data)
    if errs:
        print("INVALID:\n- " + "\n- ".join(errs))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
