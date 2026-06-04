"""Tests for the orchestrator's branching logic.

Heavy unit testing of the orchestrator is fragile (lots of mocks). We test a
few critical branches here; the real validation is the end-to-end test on a
sandbox repo (Task 12).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pr_review import orchestrator


def _setup_orchestrator_mocks(monkeypatch, *, model_output: str, existing_labels: list[str]):
    """Patch orchestrator's collaborators for end-to-end label tests.

    Returns a dict capturing label-side-effects.
    """
    captured = {"add_labels": [], "remove_labels": []}

    # Stub PR metadata, diff, ci_state, tier
    monkeypatch.setattr(
        orchestrator._pr_data, "fetch_metadata",
        lambda **_: {
            "author": "mriechers",
            "is_draft": False,
            "head_sha": "deadbeef",
            "title": "test PR",
            "body": "body",
        },
    )
    monkeypatch.setattr(orchestrator._pr_data, "detect_tier", lambda **_: "b")
    monkeypatch.setattr(orchestrator._pr_data, "fetch_ci_state", lambda **_: "success")
    monkeypatch.setattr(orchestrator._pr_data, "fetch_diff", lambda **_: "diff --git a/x b/x\n")

    # Stub prompt + LLM
    monkeypatch.setattr(orchestrator._prompt, "build", lambda **_: [{"role": "user", "content": "x"}])
    class FakeCompletion:
        content = model_output
        model = "anthropic/claude-sonnet-4-6"
        prompt_tokens = 100
        completion_tokens = 50
    monkeypatch.setattr(orchestrator._openrouter, "complete", lambda **_: FakeCompletion())
    monkeypatch.setattr(orchestrator._openrouter, "estimate_cost", lambda **_: 0.01)

    # Stub GitHub API — comments empty (so no dedup skip), token fetch, post calls
    monkeypatch.setattr(orchestrator, "_fetch_installation_token", lambda *a, **kw: "tok")
    monkeypatch.setattr(orchestrator._github_api, "fetch_pr_comment_bodies", lambda **_: [])
    monkeypatch.setattr(orchestrator._github_api, "post_pr_comment", lambda **_: "https://example.com/c")
    monkeypatch.setattr(orchestrator._github_api, "post_check_run", lambda **_: "https://example.com/check")

    # Capture label calls
    monkeypatch.setattr(orchestrator._github_api, "fetch_pr_labels", lambda **_: list(existing_labels))
    monkeypatch.setattr(
        orchestrator._github_api, "add_pr_labels",
        lambda *, token, repo, pr_number, labels: captured["add_labels"].append(tuple(labels)),
    )
    monkeypatch.setattr(
        orchestrator._github_api, "remove_pr_label",
        lambda *, token, repo, pr_number, label: captured["remove_labels"].append(label),
    )

    return captured


@pytest.fixture
def _patched_env(monkeypatch):
    """Provide the environment variables _run_inner requires."""
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("PR_WATCHER_APP_ID", "1")
    monkeypatch.setenv("PR_WATCHER_PRIVATE_KEY", "pem")
    monkeypatch.setenv("PR_WATCHER_INSTALLATION_ID", "1")


def test_orchestrator_applies_ready_label_for_severity_0(monkeypatch, _patched_env):
    """Severity 0 → orchestrator adds review:ready (no existing review labels to remove)."""
    captured = _setup_orchestrator_mocks(
        monkeypatch,
        model_output="Looks clean.\n\n<severity>0</severity>",
        existing_labels=[],
    )
    rc = orchestrator.run()
    assert rc == 0
    assert captured["add_labels"] == [("review:ready",)]
    assert captured["remove_labels"] == []


def test_orchestrator_replaces_existing_review_label(monkeypatch, _patched_env):
    """If PR has review:pending, severity 2 → remove pending, add nits."""
    captured = _setup_orchestrator_mocks(
        monkeypatch,
        model_output="Worth a look.\n\n<severity>2</severity>",
        existing_labels=["review:pending"],
    )
    rc = orchestrator.run()
    assert rc == 0
    assert captured["add_labels"] == [("review:nits",)]
    assert captured["remove_labels"] == ["review:pending"]


def test_orchestrator_skips_label_when_wip_label_present(monkeypatch, _patched_env):
    """If PR has 'wip', orchestrator posts the review but does not touch labels."""
    captured = _setup_orchestrator_mocks(
        monkeypatch,
        model_output="OK.\n\n<severity>1</severity>",
        existing_labels=["wip"],
    )
    rc = orchestrator.run()
    assert rc == 0
    assert captured["add_labels"] == []
    assert captured["remove_labels"] == []


def test_orchestrator_skips_label_when_no_pr_watch_present(monkeypatch, _patched_env):
    captured = _setup_orchestrator_mocks(
        monkeypatch,
        model_output="OK.\n\n<severity>1</severity>",
        existing_labels=["no-pr-watch"],
    )
    rc = orchestrator.run()
    assert rc == 0
    assert captured["add_labels"] == []


@pytest.fixture
def env_vars(monkeypatch):
    """Standard workflow env vars."""
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("PR_WATCHER_APP_ID", "12345")
    monkeypatch.setenv("PR_WATCHER_PRIVATE_KEY", "fake-pem")
    monkeypatch.setenv("PR_WATCHER_INSTALLATION_ID", "99")
    monkeypatch.setenv("REVIEW_MODEL", "anthropic/claude-sonnet-4-6")


def test_exit_when_pr_author_is_not_self(env_vars):
    """Self-review-only safety check: skip PRs by other users."""
    with patch.object(orchestrator, "_fetch_installation_token", return_value="tok"), \
         patch.object(orchestrator, "_pr_data") as mock_pr_data:
        mock_pr_data.fetch_metadata.return_value = {
            "author": "someone-else", "title": "T", "body": "", "head_sha": "abc", "is_draft": False,
        }
        result = orchestrator.run()
        assert result == 0
        mock_pr_data.fetch_diff.assert_not_called()


def test_exit_when_pr_is_draft(env_vars):
    """Don't review drafts. They opt-in by going Ready for review."""
    with patch.object(orchestrator, "_fetch_installation_token", return_value="tok"), \
         patch.object(orchestrator, "_pr_data") as mock_pr_data:
        mock_pr_data.fetch_metadata.return_value = {
            "author": "mriechers", "title": "T", "body": "", "head_sha": "abc", "is_draft": True,
        }
        result = orchestrator.run()
        assert result == 0
        mock_pr_data.fetch_diff.assert_not_called()


def test_dedup_skips_when_marker_for_sha_exists(env_vars):
    """If a marker for the current head SHA exists, no new review is posted."""
    with patch.object(orchestrator, "_fetch_installation_token", return_value="tok"), \
         patch.object(orchestrator, "_pr_data") as mock_pr_data, \
         patch.object(orchestrator, "_github_api") as mock_api:
        mock_pr_data.fetch_metadata.return_value = {
            "author": "mriechers", "title": "T", "body": "", "head_sha": "abc123", "is_draft": False,
        }
        mock_api.fetch_pr_comment_bodies.return_value = [
            "<!-- pr-watch-agent:\n  sha=abc123\n  ts=2026-01-01T00:00:00Z\n  model=x\n  tier=a\n  prompt_tokens=0\n  completion_tokens=0\n  cost_usd=0\n  severity=0\n  ci_state=green\n  first_run=false\n-->",
        ]
        result = orchestrator.run()
        assert result == 0
        mock_api.post_pr_comment.assert_not_called()
        mock_api.post_check_run.assert_not_called()


def test_first_run_detected_when_no_prior_markers(env_vars):
    """The first_run flag should be True when no prior pr-watch markers on this PR."""
    with patch.object(orchestrator, "_fetch_installation_token", return_value="tok"), \
         patch.object(orchestrator, "_pr_data") as mock_pr_data, \
         patch.object(orchestrator, "_github_api") as mock_api, \
         patch.object(orchestrator, "_openrouter") as mock_or, \
         patch.object(orchestrator, "_prompt") as mock_prompt:
        mock_pr_data.fetch_metadata.return_value = {
            "author": "mriechers", "title": "T", "body": "", "head_sha": "abc", "is_draft": False,
        }
        mock_pr_data.fetch_diff.return_value = "diff"
        mock_pr_data.detect_tier.return_value = "a"
        mock_pr_data.fetch_ci_state.return_value = "green"
        mock_api.fetch_pr_comment_bodies.return_value = []
        mock_or.complete.return_value = MagicMock(
            content="Review <severity>0</severity>", prompt_tokens=10, completion_tokens=5, model="x"
        )
        mock_or.estimate_cost.return_value = 0.001
        mock_prompt.build.return_value = []

        orchestrator.run()

        kwargs = mock_prompt.build.call_args.kwargs
        assert kwargs["first_run"] is True


def test_full_happy_path_posts_comment_and_check(env_vars):
    """End-to-end orchestrator happy path with all dependencies mocked."""
    with patch.object(orchestrator, "_fetch_installation_token", return_value="tok"), \
         patch.object(orchestrator, "_pr_data") as mock_pr_data, \
         patch.object(orchestrator, "_github_api") as mock_api, \
         patch.object(orchestrator, "_openrouter") as mock_or, \
         patch.object(orchestrator, "_prompt") as mock_prompt:
        mock_pr_data.fetch_metadata.return_value = {
            "author": "mriechers", "title": "Test", "body": "Desc", "head_sha": "abc", "is_draft": False,
        }
        mock_pr_data.fetch_diff.return_value = "diff text"
        mock_pr_data.detect_tier.return_value = "a"
        mock_pr_data.fetch_ci_state.return_value = "green"
        mock_api.fetch_pr_comment_bodies.return_value = []
        mock_or.complete.return_value = MagicMock(
            content="## Review\n\nLGTM\n\n<severity>1</severity>",
            prompt_tokens=200, completion_tokens=30, model="anthropic/claude-sonnet-4-6",
        )
        mock_or.estimate_cost.return_value = 0.001
        mock_prompt.build.return_value = []
        mock_api.post_pr_comment.return_value = "https://github.com/owner/repo/issues/42#issuecomment-1"

        result = orchestrator.run()
        assert result == 0
        mock_api.post_pr_comment.assert_called_once()
        mock_api.post_check_run.assert_called_once()
        check_kwargs = mock_api.post_check_run.call_args.kwargs
        assert check_kwargs["conclusion"] == "success"
        comment_body = mock_api.post_pr_comment.call_args.kwargs["body"]
        assert "<!-- pr-watch-agent:" in comment_body
        assert "<severity>" not in comment_body
        assert "LGTM" in comment_body
