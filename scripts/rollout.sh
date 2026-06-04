#!/usr/bin/env bash
# rollout.sh — deploy the PR Watcher caller workflow + secrets across the fleet.
#
# Enumerates non-archived repos for each owner, sets the 4 Actions secrets
# (personal repos only — org repos are covered by org-level secrets), and
# commits templates/pr-review-caller.yml to the default branch as
# .github/workflows/pr-review.yml. Falls back to a PR when branch protection
# rejects the direct commit. Idempotent: identical existing files are skipped.
#
# Usage:
#   scripts/rollout.sh --dry-run            # show what would happen
#   scripts/rollout.sh                      # full rollout (all owners)
#   scripts/rollout.sh --owner mriechers    # one owner only
#   scripts/rollout.sh --repo mriechers/foo # one repo only
#
# Secrets are read via get-secret.sh (Keychain/1Password shim) — never files.

set -euo pipefail

PERSONAL_OWNER="mriechers"
ORG_OWNERS=("public-media-work" "Wonder-Cabinet-Productions")
WORKFLOW_PATH=".github/workflows/pr-review.yml"
TEMPLATE="$(cd "$(dirname "$0")/.." && pwd)/templates/pr-review-caller.yml"
SECRET_NAMES=(OPENROUTER_API_KEY PR_WATCHER_APP_ID PR_WATCHER_PRIVATE_KEY PR_WATCHER_INSTALLATION_ID)

DRY_RUN=false
ONLY_OWNER=""
ONLY_REPO=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --owner) ONLY_OWNER="$2"; shift 2 ;;
    --repo) ONLY_REPO="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

get_secret() {
  # Prefer the workspace get-secret.sh shim; fall back to raw Keychain.
  if command -v get-secret.sh >/dev/null 2>&1; then
    get-secret.sh "$1" 2>/dev/null && return 0
  fi
  security find-generic-password -a "$USER" -s "developer.workspace.$1" -w 2>/dev/null
}

list_repos() {
  local owner="$1"
  local extra_filter="$2"  # jq filter fragment
  gh repo list "$owner" --no-archived --limit 200 \
    --json nameWithOwner,isFork,defaultBranchRef \
    --jq ".[] | select(.isFork|not) ${extra_filter} | \"\(.nameWithOwner)\t\(.defaultBranchRef.name)\""
}

deploy_workflow() {
  local repo="$1" branch="$2"
  local desired_b64 existing_json existing_sha existing_content

  desired_b64=$(base64 < "$TEMPLATE" | tr -d '\n')
  existing_json=$(gh api "repos/$repo/contents/$WORKFLOW_PATH?ref=$branch" 2>/dev/null || true)

  if [[ -n "$existing_json" ]]; then
    existing_sha=$(jq -r '.sha // empty' <<<"$existing_json")
    existing_content=$(jq -r '.content // empty' <<<"$existing_json" | tr -d '\n')
    if [[ "$existing_content" == "$desired_b64" ]]; then
      echo "  workflow: identical, skip"
      return 0
    fi
  else
    existing_sha=""
  fi

  if $DRY_RUN; then
    echo "  workflow: would ${existing_sha:+update}${existing_sha:-create} $WORKFLOW_PATH on $branch"
    return 0
  fi

  local args=(-X PUT "repos/$repo/contents/$WORKFLOW_PATH"
    -f message="ci: add PR Watcher caller workflow

Calls the reusable review workflow in mriechers/pr-watcher.

Agent: claude-code
Machine: $(hostname -s)

Co-Authored-By: Claude <noreply@anthropic.com>"
    -f content="$desired_b64" -f branch="$branch")
  [[ -n "$existing_sha" ]] && args+=(-f sha="$existing_sha")

  if gh api "${args[@]}" --jq '.commit.sha' 2>/dev/null; then
    echo "  workflow: committed to $branch"
  else
    echo "  workflow: direct commit failed (protection?) — opening PR"
    local pr_branch="pr-watcher-rollout"
    local base_sha
    base_sha=$(gh api "repos/$repo/git/ref/heads/$branch" --jq '.object.sha')
    gh api -X POST "repos/$repo/git/refs" \
      -f ref="refs/heads/$pr_branch" -f sha="$base_sha" >/dev/null 2>&1 || true
    local pr_args=(-X PUT "repos/$repo/contents/$WORKFLOW_PATH"
      -f message="ci: add PR Watcher caller workflow" -f content="$desired_b64" -f branch="$pr_branch")
    # Re-resolve sha on the PR branch (same as base at creation)
    local pb_sha
    pb_sha=$(gh api "repos/$repo/contents/$WORKFLOW_PATH?ref=$pr_branch" --jq '.sha' 2>/dev/null || true)
    [[ -n "$pb_sha" ]] && pr_args+=(-f sha="$pb_sha")
    gh api "${pr_args[@]}" >/dev/null
    gh pr create --repo "$repo" --base "$branch" --head "$pr_branch" \
      --title "ci: add PR Watcher caller workflow" \
      --body "Adds the PR Watcher caller. See mriechers/pr-watcher." || true
  fi
}

set_repo_secrets() {
  local repo="$1"
  if $DRY_RUN; then
    echo "  secrets: would set ${SECRET_NAMES[*]}"
    return 0
  fi
  for name in "${SECRET_NAMES[@]}"; do
    gh secret set "$name" --repo "$repo" --body "$(get_secret "$name")"
  done
  echo "  secrets: set ${#SECRET_NAMES[@]}"
}

process_repo() {
  local repo="$1" branch="$2" needs_secrets="$3"
  echo "→ $repo (default: $branch)"
  [[ "$needs_secrets" == "yes" ]] && set_repo_secrets "$repo"
  deploy_workflow "$repo" "$branch"
}

main() {
  [[ -f "$TEMPLATE" ]] || { echo "Template not found: $TEMPLATE" >&2; exit 1; }

  if [[ -n "$ONLY_REPO" ]]; then
    local branch owner
    owner="${ONLY_REPO%%/*}"
    branch=$(gh api "repos/$ONLY_REPO" --jq '.default_branch')
    local needs="no"; [[ "$owner" == "$PERSONAL_OWNER" ]] && needs="yes"
    process_repo "$ONLY_REPO" "$branch" "$needs"
    return
  fi

  # Personal repos: per-repo secrets + workflow. Skip pr-watcher itself.
  if [[ -z "$ONLY_OWNER" || "$ONLY_OWNER" == "$PERSONAL_OWNER" ]]; then
    while IFS=$'\t' read -r repo branch; do
      [[ "$repo" == "$PERSONAL_OWNER/pr-watcher" ]] && continue
      process_repo "$repo" "$branch" "yes"
    done < <(list_repos "$PERSONAL_OWNER" "")
  fi

  # Org repos: workflow only (org-level secrets cover them).
  for org in "${ORG_OWNERS[@]}"; do
    if [[ -z "$ONLY_OWNER" || "$ONLY_OWNER" == "$org" ]]; then
      while IFS=$'\t' read -r repo branch; do
        process_repo "$repo" "$branch" "no"
      done < <(list_repos "$org" "")
    fi
  done
}

main
