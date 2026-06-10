# Maintainer notes (Luc) — one-time setup

This directory is the TEMPLATE for the shared leaderboard repo. Create the real
repo once:

    cp -R templates/leaderboard-repo /tmp/vibe-trade-leaderboard
    cd /tmp/vibe-trade-leaderboard
    git init -b main && git add -A && git commit -m "leaderboard: initial"
    gh repo create vibe-trade-leaderboard --public --source=. --push

**Public on purpose:** friends fork it, and the front page *is* the leaderboard.
(Forks must stay public too — the auto-merge workflow reads the score file from
the fork via the API, which the repo's Action token can't do on a private fork.)
Only percentages and dates ever live here — the validator rejects any
account-state key; dollar baselines stay in each friend's private strategy repo.

After creating: nothing to maintain. Score PRs auto-merge when they pass the
guard (`.github/workflows/validate-and-merge.yml`); the README re-renders on
every merged score (`render.yml`). PRs that fail the guard stay open with a
comment for you to eyeball.
