#!/usr/bin/env bash
# Idempotently create the four review:* labels in a GitHub repository.
#
# Usage:
#   ./bootstrap_labels.sh                    # current dir's repo
#   ./bootstrap_labels.sh --repo OWNER/NAME  # explicit repo
#
# Used by /modernize-repo for per-repo bootstrap. Safe to re-run.

set -euo pipefail

REPO_ARG=()
if [[ "${1:-}" == "--repo" ]]; then
    if [[ -z "${2:-}" ]]; then
        echo "Usage: $0 [--repo OWNER/NAME]" >&2
        exit 1
    fi
    REPO_ARG=(--repo "$2")
fi

# Format: "name|color|description"
declare -a LABELS=(
    "review:pending|cfd3d7|Bot reviewer has not run yet on this SHA."
    "review:ready|0e8a16|Bot reviewer found no concerns — merge me."
    "review:nits|fbca04|Bot reviewer found minor things — glance and merge."
    "review:blocker|d73a4a|Bot reviewer found blockers — needs work before merge."
)

for entry in "${LABELS[@]}"; do
    IFS='|' read -r name color desc <<< "$entry"
    gh label create "$name" \
        --color "$color" \
        --description "$desc" \
        --force \
        "${REPO_ARG[@]}"
done

echo "Seeded ${#LABELS[@]} review:* labels"
