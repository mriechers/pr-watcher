# pr-watcher

Async PR review bot. A GitHub App ("PR Watcher") + reusable Actions workflow that
posts an LLM review comment on every push to a self-authored PR, calibrated to the
repo's CI tier. Extracted from `the-lodge` so any repo — personal or org — can call
the same reusable workflow.

## How it works

1. A 25-line **caller workflow** in each repo fires on PR events (and
   `workflow_dispatch` for manual/backfill runs).
2. It calls the **reusable workflow** here (`pr-review-reusable.yml`), which checks
   out this repo, installs deps, and runs `pr_review.orchestrator`.
3. The orchestrator mints a GitHub App installation token, performs safety checks
   (self-authored only, not draft, SHA not already reviewed), builds a tier-aware
   prompt with the diff + CI state, calls OpenRouter, and posts the review comment +
   check run.

State lives in marker comments (`<!-- pr-watch-agent: sha=... -->`) — re-runs on the
same SHA are no-ops.

## Setup for a new repo

1. **Install the App** on the repo (or org) — `github.com/settings/installations`.
2. **Secrets** (repo- or org-level Actions secrets):
   `OPENROUTER_API_KEY`, `PR_WATCHER_APP_ID`, `PR_WATCHER_PRIVATE_KEY`,
   `PR_WATCHER_INSTALLATION_ID` (note: installation IDs are per-account/org).
3. **Caller workflow**: copy `templates/pr-review-caller.yml` to
   `.github/workflows/pr-review.yml`.

Or run `scripts/rollout.sh` which does 2–3 for the whole fleet.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/rollout.sh` | Fan out secrets + caller workflow to all non-archived repos (`--dry-run` supported) |
| `scripts/backfill-reviews.sh` | Dispatch a review for every open self-authored PR (idempotent) |

## Opting out

- Mark the PR as **draft** (reviewed when it goes ready-for-review)
- PRs by other authors are skipped automatically (`SELF_REVIEW_AUTHOR`, default `mriechers`)

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest pr_review/tests/
```

Review tiers come from repo topics (`tier-a`, `tier-b`, `tier-floor`); untagged
repos default to tier B. Model defaults to `anthropic/claude-sonnet-4-6` via
OpenRouter (override with the `model` input).
