"""Tests for PR data fetching."""
from __future__ import annotations

from pr_review import pr_data


def test_fetch_diff(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/pulls/42",
        method="GET",
        match_headers={"Accept": "application/vnd.github.v3.diff"},
        text="--- a/foo\n+++ b/foo\n@@ -1 +1 @@\n-old\n+new\n",
    )

    diff = pr_data.fetch_diff(token="ghs_test", repo="owner/repo", pr_number=42)
    assert "--- a/foo" in diff


def test_fetch_pr_metadata(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/pulls/42",
        method="GET",
        match_headers={"Accept": "application/vnd.github+json"},
        json={
            "title": "Add feature X",
            "body": "Description here.",
            "user": {"login": "mriechers"},
            "head": {"sha": "abc123def"},
            "draft": False,
        },
    )

    meta = pr_data.fetch_metadata(token="ghs_test", repo="owner/repo", pr_number=42)
    assert meta["title"] == "Add feature X"
    assert meta["body"] == "Description here."
    assert meta["author"] == "mriechers"
    assert meta["head_sha"] == "abc123def"
    assert meta["is_draft"] is False


def test_detect_tier_from_topics_a(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/topics",
        method="GET",
        json={"names": ["tier-a", "python", "automation"]},
    )

    tier = pr_data.detect_tier(token="ghs_test", repo="owner/repo")
    assert tier == "a"


def test_detect_tier_from_topics_b(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/topics",
        method="GET",
        json={"names": ["tier-b"]},
    )

    tier = pr_data.detect_tier(token="ghs_test", repo="owner/repo")
    assert tier == "b"


def test_detect_tier_from_topics_floor(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/topics",
        method="GET",
        json={"names": ["tier-floor", "archived"]},
    )

    tier = pr_data.detect_tier(token="ghs_test", repo="owner/repo")
    assert tier == "floor"


def test_detect_tier_defaults_to_b_when_no_topic(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/topics",
        method="GET",
        json={"names": ["python", "automation"]},
    )

    tier = pr_data.detect_tier(token="ghs_test", repo="owner/repo")
    assert tier == "b"


def test_fetch_ci_state_green(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/commits/abc123/check-runs",
        method="GET",
        json={
            "check_runs": [
                {"name": "lint", "status": "completed", "conclusion": "success"},
                {"name": "test", "status": "completed", "conclusion": "success"},
            ],
        },
    )

    state = pr_data.fetch_ci_state(token="ghs_test", repo="owner/repo", head_sha="abc123")
    assert state == "green"


def test_fetch_ci_state_failing(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/commits/abc123/check-runs",
        method="GET",
        json={
            "check_runs": [
                {"name": "lint", "status": "completed", "conclusion": "success"},
                {"name": "test", "status": "completed", "conclusion": "failure"},
            ],
        },
    )

    state = pr_data.fetch_ci_state(token="ghs_test", repo="owner/repo", head_sha="abc123")
    assert state == "failing"


def test_fetch_ci_state_pending(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/commits/abc123/check-runs",
        method="GET",
        json={
            "check_runs": [
                {"name": "lint", "status": "completed", "conclusion": "success"},
                {"name": "test", "status": "in_progress", "conclusion": None},
            ],
        },
    )

    state = pr_data.fetch_ci_state(token="ghs_test", repo="owner/repo", head_sha="abc123")
    assert state == "pending"


def test_fetch_ci_state_none_when_no_checks(httpx_mock):
    """When the repo has no CI configured at all, ci_state is 'none'.

    Our own Claude-review check is filtered out so it doesn't count as 'CI'.
    """
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/commits/abc123/check-runs",
        method="GET",
        json={"check_runs": [{"name": "Claude review", "status": "completed", "conclusion": "success"}]},
    )

    state = pr_data.fetch_ci_state(token="ghs_test", repo="owner/repo", head_sha="abc123")
    assert state == "none"
