"""Tests for the one-time backfill that retroactively applies review:* labels."""
from __future__ import annotations

from pr_review import backfill_labels


def test_extract_severity_from_marker_finds_severity_2():
    body = """<!-- pr-watch-agent:
  sha=abc123
  ts=2026-05-21T22:18:59Z
  model=anthropic/claude-4.6-sonnet-20260217
  tier=b
  severity=2
  ci_state=pending
  first_run=true
-->

Review text here."""
    assert backfill_labels.extract_severity(body) == 2


def test_extract_severity_returns_none_when_marker_absent():
    body = "Just a regular comment, no marker."
    assert backfill_labels.extract_severity(body) is None


def test_extract_severity_returns_none_for_malformed_marker():
    body = "<!-- pr-watch-agent: severity=banana -->"
    assert backfill_labels.extract_severity(body) is None


def test_extract_severity_handles_severity_negative_one():
    """-1 is the orchestrator's sentinel for 'severity not parsed'."""
    body = "<!-- pr-watch-agent:\n  sha=x\n  severity=-1\n-->"
    assert backfill_labels.extract_severity(body) == -1


def test_pick_label_uses_latest_bot_review():
    """Given multiple bot review comments, pick the most recent severity."""
    comments = [
        {"body": "<!-- pr-watch-agent:\n  severity=3\n-->", "createdAt": "2026-05-20T10:00:00Z"},
        {"body": "<!-- pr-watch-agent:\n  severity=1\n-->", "createdAt": "2026-05-21T10:00:00Z"},
    ]
    assert backfill_labels.pick_label_for_pr(comments) == "review:ready"


def test_pick_label_for_pr_with_no_reviews_returns_pending():
    assert backfill_labels.pick_label_for_pr([]) == "review:pending"


def test_pick_label_ignores_non_marker_comments():
    comments = [
        {"body": "Hey just checking on this", "createdAt": "2026-05-21T10:00:00Z"},
        {"body": "<!-- pr-watch-agent:\n  severity=2\n-->", "createdAt": "2026-05-20T10:00:00Z"},
    ]
    assert backfill_labels.pick_label_for_pr(comments) == "review:nits"
