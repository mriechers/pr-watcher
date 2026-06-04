"""Tests for GitHub API operations (comments + check runs)."""
from __future__ import annotations

import json

import pytest

from pr_review import github_api


def test_fetch_pr_comment_bodies(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/issues/42/comments?per_page=100",
        method="GET",
        json=[
            {"body": "first comment", "id": 1},
            {"body": "<!-- pr-watch-agent:\n  sha=abc\n-->\n## Review\nLooks good", "id": 2},
        ],
    )

    bodies = github_api.fetch_pr_comment_bodies(
        token="ghs_test",
        repo="owner/repo",
        pr_number=42,
    )
    assert len(bodies) == 2
    assert bodies[1].startswith("<!-- pr-watch-agent:")


def test_fetch_pr_comment_bodies_paginates(httpx_mock):
    """Multi-page response: follows Link: rel='next' until exhausted."""
    page2_url = "https://api.github.com/repos/owner/repo/issues/42/comments?per_page=100&page=2"
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/issues/42/comments?per_page=100",
        method="GET",
        json=[{"body": f"comment-{i}", "id": i} for i in range(100)],
        headers={"Link": f'<{page2_url}>; rel="next", <...>; rel="last"'},
    )
    httpx_mock.add_response(
        url=page2_url,
        method="GET",
        json=[{"body": f"comment-{i}", "id": i} for i in range(100, 150)],
        # No Link: rel="next" → loop exits.
    )

    bodies = github_api.fetch_pr_comment_bodies(
        token="ghs_test",
        repo="owner/repo",
        pr_number=42,
    )
    assert len(bodies) == 150
    assert bodies[0] == "comment-0"
    assert bodies[-1] == "comment-149"


def test_post_pr_comment(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/issues/42/comments",
        method="POST",
        status_code=201,
        json={"id": 999, "html_url": "https://github.com/owner/repo/issues/42#issuecomment-999"},
    )

    url = github_api.post_pr_comment(
        token="ghs_test",
        repo="owner/repo",
        pr_number=42,
        body="<!-- marker --> Review body",
    )

    request = httpx_mock.get_request()
    assert request.headers["Authorization"] == "Bearer ghs_test"
    assert json.loads(request.content) == {"body": "<!-- marker --> Review body"}
    assert url == "https://github.com/owner/repo/issues/42#issuecomment-999"


def test_post_pr_comment_raises_on_error(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/issues/42/comments",
        method="POST",
        status_code=403,
        json={"message": "Forbidden"},
    )

    with pytest.raises(github_api.GitHubAPIError):
        github_api.post_pr_comment(
            token="ghs_test",
            repo="owner/repo",
            pr_number=42,
            body="body",
        )


def test_post_check_run_with_success(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/check-runs",
        method="POST",
        status_code=201,
        json={"id": 12345, "html_url": "https://github.com/owner/repo/runs/12345"},
    )

    url = github_api.post_check_run(
        token="ghs_test",
        repo="owner/repo",
        head_sha="abc123",
        conclusion="success",
        title="Claude review",
        summary="Clean diff, green CI",
        details_url="https://github.com/owner/repo/issues/42#issuecomment-999",
    )

    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["name"] == "Claude review"
    assert body["head_sha"] == "abc123"
    assert body["conclusion"] == "success"
    assert body["status"] == "completed"
    assert body["output"]["title"] == "Claude review"
    assert body["output"]["summary"] == "Clean diff, green CI"
    assert body["details_url"].endswith("issuecomment-999")
    assert url == "https://github.com/owner/repo/runs/12345"


def test_post_check_run_with_action_required(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/check-runs",
        method="POST",
        status_code=201,
        json={"id": 12345, "html_url": "x"},
    )

    github_api.post_check_run(
        token="ghs_test",
        repo="owner/repo",
        head_sha="abc",
        conclusion="action_required",
        title="Claude review",
        summary="Blocker — fix before merging",
        details_url="x",
    )

    body = json.loads(httpx_mock.get_request().content)
    assert body["conclusion"] == "action_required"


def test_fetch_pr_labels_returns_names(monkeypatch):
    """fetch_pr_labels returns just the label names from the API response."""
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return [
                {"name": "wip", "color": "ccc"},
                {"name": "review:ready", "color": "0e8a16"},
            ]

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return FakeResponse()

    monkeypatch.setattr(github_api.httpx, "get", fake_get)
    labels = github_api.fetch_pr_labels(token="t", repo="owner/repo", pr_number=42)
    assert labels == ["wip", "review:ready"]
    assert "/repos/owner/repo/issues/42/labels" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer t"


def test_add_pr_labels_posts_payload(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return []

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResponse()

    monkeypatch.setattr(github_api.httpx, "post", fake_post)
    github_api.add_pr_labels(
        token="t", repo="owner/repo", pr_number=42, labels=["review:ready"]
    )
    assert captured["url"].endswith("/issues/42/labels")
    assert captured["json"] == {"labels": ["review:ready"]}


def test_add_pr_labels_is_noop_for_empty_list(monkeypatch):
    """Calling with [] should not hit the API at all."""
    called = []

    def fake_post(*args, **kwargs):
        called.append(args)
        raise AssertionError("should not have been called")

    monkeypatch.setattr(github_api.httpx, "post", fake_post)
    github_api.add_pr_labels(token="t", repo="owner/repo", pr_number=42, labels=[])
    assert called == []


def test_remove_pr_label_calls_delete(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

    def fake_delete(url, **kwargs):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(github_api.httpx, "delete", fake_delete)
    github_api.remove_pr_label(
        token="t", repo="owner/repo", pr_number=42, label="review:ready"
    )
    # URL-encoded label name in the path — `safe=""` always encodes the colon
    assert "/issues/42/labels/review%3Aready" in captured["url"]


def test_remove_pr_label_swallows_404(monkeypatch):
    """Removing a label that isn't present is a no-op, not an error."""

    class FakeResponse:
        status_code = 404
        text = "Label does not exist"

    def fake_delete(url, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(github_api.httpx, "delete", fake_delete)
    # Should not raise
    github_api.remove_pr_label(
        token="t", repo="owner/repo", pr_number=42, label="review:ready"
    )


def test_remove_pr_label_raises_on_500(monkeypatch):
    class FakeResponse:
        status_code = 500
        text = "Server error"

    def fake_delete(url, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(github_api.httpx, "delete", fake_delete)
    with pytest.raises(github_api.GitHubAPIError):
        github_api.remove_pr_label(
            token="t", repo="owner/repo", pr_number=42, label="review:ready"
        )
