#!/usr/bin/env python3
"""One-time backfill: apply review:* labels to existing open PRs by reading
their most recent bot review marker.

PRs with no bot review yet get `review:pending`. PRs with `wip` or
`no-pr-watch` are skipped (matching the orchestrator's policy).

This script uses the local user's `gh` CLI auth (not the App), so it works
from an interactive terminal. Run it once after the orchestrator change
ships and the labels are bootstrapped.

Usage:
    python3 backfill_labels.py              # current dir's repo
    python3 backfill_labels.py --repo OWNER/NAME
    python3 backfill_labels.py --dry-run    # print plan, don't modify
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Make `scripts/` importable so `from pr_review import labels` works when
# running this file directly (e.g., `python3 backfill_labels.py`).
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pr_review import labels as _labels  # noqa: E402

_MARKER_OPEN_RE = re.compile(r"<!--\s*pr-watch-agent:")
_MARKER_SEVERITY_RE = re.compile(r"severity\s*=\s*(-?\d+)", re.MULTILINE)


def extract_severity(comment_body: str) -> int | None:
    """Parse `severity=N` out of a pr-watch-agent marker. Returns None if
    the marker is absent or the value is non-integer.
    """
    if not _MARKER_OPEN_RE.search(comment_body):
        return None
    match = _MARKER_SEVERITY_RE.search(comment_body)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def pick_label_for_pr(comments: list[dict]) -> str:
    """Choose a review:* label based on the most recent bot review marker.

    Comments are expected to be dicts with `body` and `createdAt` keys
    (the shape `gh pr view --json comments` returns).
    """
    bot_reviews = [
        (c.get("createdAt", ""), c["body"])
        for c in comments
        if _MARKER_OPEN_RE.search(c.get("body", ""))
    ]
    if not bot_reviews:
        return "review:pending"
    bot_reviews.sort(reverse=True)
    _, latest_body = bot_reviews[0]
    severity = extract_severity(latest_body)
    if severity == -1:
        # Orchestrator sentinel for "model output didn't include severity" —
        # treat as pending (the next push will resolve it).
        return "review:pending"
    return _labels.severity_to_label(severity)


def _gh_json(args: list[str]) -> object:
    """Run `gh ... --json ...` and return parsed JSON."""
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def _set_label_exclusive(repo_arg: list[str], pr_number: int, target: str) -> None:
    """Remove any existing review:* labels on the PR, then add the target."""
    pr = _gh_json([
        "pr", "view", str(pr_number),
        "--json", "labels",
        *repo_arg,
    ])
    current = [lbl["name"] for lbl in pr.get("labels", [])]
    to_remove = [name for name in current if _labels.is_review_label(name) and name != target]
    for name in to_remove:
        subprocess.run(
            ["gh", "pr", "edit", str(pr_number), "--remove-label", name, *repo_arg],
            check=True,
        )
    if target not in current:
        subprocess.run(
            ["gh", "pr", "edit", str(pr_number), "--add-label", target, *repo_arg],
            check=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="OWNER/NAME (default: current dir's repo)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done, don't modify labels.")
    args = parser.parse_args(argv)

    repo_arg = ["--repo", args.repo] if args.repo else []

    open_prs = _gh_json([
        "pr", "list", "--state", "open",
        "--json", "number,title,labels",
        *repo_arg,
    ])

    if not open_prs:
        print("No open PRs.")
        return 0

    for pr in open_prs:
        pr_number = pr["number"]
        current_labels = {lbl["name"] for lbl in pr.get("labels", [])}

        if _labels.SUPPRESS_LABELS & current_labels:
            print(f"#{pr_number}: skip (suppress label: "
                  f"{sorted(_labels.SUPPRESS_LABELS & current_labels)})")
            continue

        comments = _gh_json([
            "pr", "view", str(pr_number),
            "--json", "comments",
            *repo_arg,
        ]).get("comments", [])

        target = pick_label_for_pr(comments)
        print(f"#{pr_number}: {pr['title'][:60]} → {target}")
        if args.dry_run:
            continue
        _set_label_exclusive(repo_arg, pr_number, target)

    return 0


if __name__ == "__main__":
    sys.exit(main())
