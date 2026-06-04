"""Map model severity output (0-3) to GitHub check-run conclusions.

Severity 0 = clean diff, green CI. No issues found.
Severity 1 = nits only. Style/minor things, not merge-blockers.
Severity 2 = worth a look. Genuine concern, but not a blocker — read before merging.
Severity 3 = blocker. Failing CI, broken logic, security concern, or similar.

The check-run conclusion mapping is the at-a-glance signal in the PR list:
  0/1 → success    (✓ green checkmark)
  2   → neutral    (○ gray circle — read before merging)
  3   → action_required (⚠ orange — address before merging)

Per the spec, the check is informational only (not in branch protection).
"""
from __future__ import annotations

import re

_SEVERITY_RE = re.compile(r"<severity>\s*(-?\d+)\s*</severity>")
_VALID_SEVERITIES = {0, 1, 2, 3}

_CONCLUSION_MAP = {
    0: "success",
    1: "success",
    2: "neutral",
    3: "action_required",
}

_SUMMARY_MAP = {
    0: "Clean diff, green CI",
    1: "Nits only — safe to merge",
    2: "Worth a look before merging",
    3: "Blocker — fix before merging",
}


def extract(model_text: str) -> int | None:
    """Pull the severity integer out of model output. Returns None if missing/invalid."""
    match = _SEVERITY_RE.search(model_text)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    if value not in _VALID_SEVERITIES:
        return None
    return value


def to_check_conclusion(sev: int | None) -> str:
    """Map severity to a GitHub check-run conclusion string."""
    if sev is None:
        return "neutral"
    if sev not in _CONCLUSION_MAP:
        raise ValueError(f"Invalid severity: {sev}")
    return _CONCLUSION_MAP[sev]


def summary(sev: int | None) -> str:
    """One-line summary for the check-run output panel."""
    if sev is None:
        return "Review posted (severity not parsed)"
    return _SUMMARY_MAP.get(sev, "Unknown severity")
