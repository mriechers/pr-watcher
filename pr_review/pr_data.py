"""Fetch PR metadata, diff, repo topics (for tier), and CI summary from GitHub."""
from __future__ import annotations

import httpx

_GITHUB_API = "https://api.github.com"
_TIMEOUT_SECONDS = 30
_HEADERS_BASE = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
_OUR_CHECK_NAME = "Claude review"
_VALID_TIERS = {"a", "b", "floor"}


def fetch_diff(*, token: str, repo: str, pr_number: int) -> str:
    """Fetch the PR's unified diff text."""
    headers = {**_HEADERS_BASE, "Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github.v3.diff"}
    response = httpx.get(
        f"{_GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers=headers,
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.text


def fetch_metadata(*, token: str, repo: str, pr_number: int) -> dict:
    """Fetch PR title, body, author, head SHA, draft state."""
    headers = {**_HEADERS_BASE, "Authorization": f"Bearer {token}"}
    response = httpx.get(
        f"{_GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers=headers,
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "title": data["title"],
        "body": data.get("body") or "",
        "author": data["user"]["login"],
        "head_sha": data["head"]["sha"],
        "is_draft": data.get("draft", False),
    }


def detect_tier(*, token: str, repo: str) -> str:
    """Read repo topics to determine tier. Defaults to 'b' if no tier topic present."""
    headers = {**_HEADERS_BASE, "Authorization": f"Bearer {token}"}
    response = httpx.get(
        f"{_GITHUB_API}/repos/{repo}/topics",
        headers=headers,
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    topics = response.json().get("names", [])
    for topic in topics:
        if topic.startswith("tier-"):
            tier_value = topic[len("tier-"):]
            if tier_value in _VALID_TIERS:
                return tier_value
    return "b"


def fetch_ci_state(*, token: str, repo: str, head_sha: str) -> str:
    """Summarize CI state for a commit. Returns 'green', 'failing', 'pending', or 'none'.

    Filters out our own Claude review check so it doesn't influence the summary.
    """
    headers = {**_HEADERS_BASE, "Authorization": f"Bearer {token}"}
    response = httpx.get(
        f"{_GITHUB_API}/repos/{repo}/commits/{head_sha}/check-runs",
        headers=headers,
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    check_runs = [
        r for r in response.json().get("check_runs", [])
        if r.get("name") != _OUR_CHECK_NAME
    ]
    if not check_runs:
        return "none"
    if any(r.get("status") != "completed" for r in check_runs):
        return "pending"
    if any(r.get("conclusion") not in ("success", "neutral", "skipped") for r in check_runs):
        return "failing"
    return "green"
