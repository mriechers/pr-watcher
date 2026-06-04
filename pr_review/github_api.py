"""GitHub REST API operations for PR comments and check runs.

All operations use a GitHub App installation token (passed in by the caller).
Comments are posted via the Issues API (PRs are issues); check runs via the
Checks API.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx

_GITHUB_API = "https://api.github.com"
_TIMEOUT_SECONDS = 30
_HEADERS_BASE = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class GitHubAPIError(RuntimeError):
    """Raised on non-2xx response from a GitHub API call."""


def fetch_pr_comment_bodies(*, token: str, repo: str, pr_number: int) -> list[str]:
    """Return all comment bodies on a PR (paginated). Used for marker dedup."""
    bodies: list[str] = []
    url: str | None = f"{_GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    params: dict[str, int] | None = {"per_page": 100}
    while url:
        response = httpx.get(
            url,
            headers=_auth(token),
            params=params,
            timeout=_TIMEOUT_SECONDS,
        )
        _raise_on_error(response, "fetch PR comments")
        bodies.extend(c["body"] for c in response.json())
        url = _next_page_url(response.headers.get("Link"))
        params = None  # next-page URL already encodes per_page and page args
    return bodies


def _next_page_url(link_header: str | None) -> str | None:
    """Extract the URL from a GitHub Link header's rel="next" entry, if present."""
    if not link_header:
        return None
    for part in link_header.split(","):
        segment, _, rel = part.partition(";")
        if 'rel="next"' in rel:
            return segment.strip().lstrip("<").rstrip(">")
    return None


def post_pr_comment(*, token: str, repo: str, pr_number: int, body: str) -> str:
    """Post a comment on a PR. Returns the comment's html_url."""
    response = httpx.post(
        f"{_GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
        headers=_auth(token),
        json={"body": body},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_on_error(response, "post PR comment")
    return response.json()["html_url"]


def post_check_run(
    *,
    token: str,
    repo: str,
    head_sha: str,
    conclusion: str,
    title: str,
    summary: str,
    details_url: str,
) -> str:
    """Post a check run for a commit. Returns the check run's html_url."""
    payload = {
        "name": "Claude review",
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": conclusion,
        "details_url": details_url,
        "output": {
            "title": title,
            "summary": summary,
        },
    }
    response = httpx.post(
        f"{_GITHUB_API}/repos/{repo}/check-runs",
        headers=_auth(token),
        json=payload,
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_on_error(response, "post check run")
    return response.json()["html_url"]


def fetch_pr_labels(*, token: str, repo: str, pr_number: int) -> list[str]:
    """Return the names of all labels currently on a PR."""
    response = httpx.get(
        f"{_GITHUB_API}/repos/{repo}/issues/{pr_number}/labels",
        headers=_auth(token),
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_on_error(response, "fetch PR labels")
    return [label["name"] for label in response.json()]


def add_pr_labels(
    *, token: str, repo: str, pr_number: int, labels: list[str]
) -> None:
    """Add one or more labels to a PR. No-op if labels is empty."""
    if not labels:
        return
    response = httpx.post(
        f"{_GITHUB_API}/repos/{repo}/issues/{pr_number}/labels",
        headers=_auth(token),
        json={"labels": labels},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_on_error(response, "add PR labels")


def remove_pr_label(
    *, token: str, repo: str, pr_number: int, label: str
) -> None:
    """Remove a single label from a PR. A 404 (label not present) is OK."""
    encoded = quote(label, safe="")
    response = httpx.delete(
        f"{_GITHUB_API}/repos/{repo}/issues/{pr_number}/labels/{encoded}",
        headers=_auth(token),
        timeout=_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return  # Label wasn't there; nothing to remove
    _raise_on_error(response, f"remove PR label {label!r}")


def _auth(token: str) -> dict[str, str]:
    return {**_HEADERS_BASE, "Authorization": f"Bearer {token}"}


def _raise_on_error(response: httpx.Response, action: str) -> None:
    if response.status_code >= 400:
        raise GitHubAPIError(
            f"Failed to {action} ({response.status_code}): {response.text[:500]}"
        )
