#!/usr/bin/env bash
# backfill-reviews.sh — trigger a PR Watcher review for every open self-authored PR.
#
# Safe to re-run: the orchestrator dedups by head-SHA marker comment, so PRs
# already reviewed at their current SHA are no-ops. Drafts are skipped by the
# orchestrator's draft check.
#
# Usage:
#   scripts/backfill-reviews.sh --dry-run
#   scripts/backfill-reviews.sh
#   scripts/backfill-reviews.sh --repo mriechers/cardigan   # one repo only

set -euo pipefail

DRY_RUN=false
ONLY_REPO=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --repo) ONLY_REPO="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

while IFS=$'\t' read -r repo number title; do
  [[ -n "$ONLY_REPO" && "$repo" != "$ONLY_REPO" ]] && continue
  if $DRY_RUN; then
    echo "would dispatch: $repo#$number  $title"
    continue
  fi
  if gh workflow run pr-review.yml --repo "$repo" -f pr_number="$number" 2>/dev/null; then
    echo "dispatched: $repo#$number"
  else
    echo "FAILED (no workflow yet?): $repo#$number" >&2
  fi
  sleep 2  # be gentle with the API
done < <(gh search prs --author "@me" --state open --limit 100 \
  --json repository,number,title \
  --jq '.[] | "\(.repository.nameWithOwner)\t\(.number)\t\(.title)"')
