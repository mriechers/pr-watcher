"""Review label catalog and severity-to-label mapping.

The four `review:*` labels carry the bot reviewer's verdict to GitHub's UI,
so PRs can be triaged at a glance without opening Claude Code. Exactly one
label is set per PR by the orchestrator; this module is pure (no I/O).
"""
from __future__ import annotations

REVIEW_LABELS: dict[str, dict[str, str]] = {
    "review:pending": {
        "color": "cfd3d7",
        "description": "Bot reviewer has not run yet on this SHA.",
    },
    "review:ready": {
        "color": "0e8a16",
        "description": "Bot reviewer found no concerns — merge me.",
    },
    "review:nits": {
        "color": "fbca04",
        "description": "Bot reviewer found minor things — glance and merge.",
    },
    "review:blocker": {
        "color": "d73a4a",
        "description": "Bot reviewer found blockers — needs work before merge.",
    },
}

# Labels that, when present on a PR, suppress reviewer label-application.
SUPPRESS_LABELS: set[str] = {"wip", "no-pr-watch"}


def all_review_labels() -> list[str]:
    """Return the canonical list of review label names."""
    return list(REVIEW_LABELS.keys())


def is_review_label(name: str) -> bool:
    """Return True iff the given name is one of the four review:* labels."""
    return name in REVIEW_LABELS


def severity_to_label(severity: int | None) -> str:
    """Map a reviewer severity score (0..3) to its label.

    None or out-of-range values map to `review:pending` — used when the
    reviewer failed to parse severity from model output (which usually
    indicates a degraded run).
    """
    if severity is None or severity not in (0, 1, 2, 3):
        return "review:pending"
    if severity <= 1:
        return "review:ready"
    if severity == 2:
        return "review:nits"
    return "review:blocker"
