"""Main entry point for the GH Actions workflow.

Reads env vars set by the workflow, performs the self-review safety check,
dedups against existing markers, builds the prompt, calls OpenRouter, posts
the review comment and check run.

Exit codes:
  0 — success (review posted, OR safety check / dedup short-circuited)
  1 — unexpected error (workflow shows red)
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
import traceback

# Module aliases enable easy mocking in tests.
from pr_review import github_api as _github_api
from pr_review import github_app as _github_app
from pr_review import labels as _labels
from pr_review import marker as _marker
from pr_review import openrouter as _openrouter
from pr_review import pr_data as _pr_data
from pr_review import prompt as _prompt
from pr_review import severity as _severity

SELF_REVIEW_AUTHOR = os.environ.get("SELF_REVIEW_AUTHOR", "mriechers")
_SEVERITY_STRIP_RE = re.compile(r"\n*\s*<severity>\s*-?\d+\s*</severity>\s*\n*$")


def run() -> int:
    """Orchestrate one PR review run. Returns process exit code."""
    try:
        return _run_inner()
    except Exception:
        traceback.print_exc()
        return 1


def _run_inner() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["PR_NUMBER"])
    openrouter_key = os.environ["OPENROUTER_API_KEY"]
    app_id = os.environ["PR_WATCHER_APP_ID"]
    private_key = os.environ["PR_WATCHER_PRIVATE_KEY"]
    installation_id = os.environ["PR_WATCHER_INSTALLATION_ID"]
    model = os.environ.get("REVIEW_MODEL", "anthropic/claude-sonnet-4-6")

    token = _fetch_installation_token(app_id, private_key, installation_id)

    metadata = _pr_data.fetch_metadata(token=token, repo=repo, pr_number=pr_number)

    if metadata["author"] != SELF_REVIEW_AUTHOR:
        print(f"Skipping: PR authored by {metadata['author']!r}, not {SELF_REVIEW_AUTHOR!r}.")
        return 0

    if metadata["is_draft"]:
        print("Skipping: PR is a draft.")
        return 0

    head_sha = metadata["head_sha"]

    existing_comments = _github_api.fetch_pr_comment_bodies(
        token=token, repo=repo, pr_number=pr_number
    )
    reviewed_shas = _marker.shas_in_comments(existing_comments)
    if head_sha in reviewed_shas:
        print(f"Skipping: SHA {head_sha} already reviewed.")
        return 0

    first_run = len(reviewed_shas) == 0
    tier = _pr_data.detect_tier(token=token, repo=repo)
    ci_state = _pr_data.fetch_ci_state(token=token, repo=repo, head_sha=head_sha)
    diff = _pr_data.fetch_diff(token=token, repo=repo, pr_number=pr_number)

    messages = _prompt.build(
        diff=diff,
        tier=tier,
        ci_state=ci_state,
        first_run=first_run,
        pr_title=metadata["title"],
        pr_body=metadata["body"],
    )

    completion = _openrouter.complete(
        api_key=openrouter_key,
        model=model,
        messages=messages,
    )

    sev = _severity.extract(completion.content)
    conclusion = _severity.to_check_conclusion(sev)
    summary_line = _severity.summary(sev)
    # Use the requested model name for cost lookup, not the response's resolved
    # variant. OpenRouter often returns date-pinned IDs (e.g. claude-4.6-sonnet-
    # 20260217) that don't match our pricing table keys. The pricing tier is
    # determined by what we asked for, not by what dated variant they resolved
    # to. The marker still records completion.model for accuracy on what ran.
    cost = _openrouter.estimate_cost(
        model=model,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
    )

    marker_text = _marker.serialize({
        "sha": head_sha,
        "ts": _now_iso(),
        "model": completion.model,
        "tier": tier,
        "prompt_tokens": completion.prompt_tokens,
        "completion_tokens": completion.completion_tokens,
        "cost_usd": round(cost, 4),
        "severity": sev if sev is not None else -1,
        "ci_state": ci_state,
        "first_run": first_run,
    })

    review_body = _SEVERITY_STRIP_RE.sub("", completion.content).strip()
    comment_body = (
        f"{marker_text}\n\n{review_body}\n\n---\n"
        "*\U0001F44D helpful · \U0001F44E noise · \U0001F916 wrong call — react to give the bot feedback*"
    )

    comment_url = _github_api.post_pr_comment(
        token=token, repo=repo, pr_number=pr_number, body=comment_body
    )

    _github_api.post_check_run(
        token=token,
        repo=repo,
        head_sha=head_sha,
        conclusion=conclusion,
        title="Claude review",
        summary=summary_line,
        details_url=comment_url,
    )

    _apply_review_label(
        token=token,
        repo=repo,
        pr_number=pr_number,
        severity=sev,
    )

    print(f"Posted review to {comment_url} (severity={sev}, conclusion={conclusion}, cost=${cost:.4f})")
    return 0


def _apply_review_label(
    *, token: str, repo: str, pr_number: int, severity: int | None
) -> None:
    """Replace any review:* labels with the one matching this severity.

    Skips entirely if the PR carries a suppress label (wip / no-pr-watch).
    """
    current = _github_api.fetch_pr_labels(token=token, repo=repo, pr_number=pr_number)
    current_set = set(current)
    suppress_hits = _labels.SUPPRESS_LABELS & current_set
    if suppress_hits:
        print(f"Skipping label: PR has suppress label ({sorted(suppress_hits)})")
        return

    target = _labels.severity_to_label(severity)
    existing_review = {name for name in current_set if _labels.is_review_label(name)}
    to_remove = existing_review - {target}

    for label_name in sorted(to_remove):
        _github_api.remove_pr_label(
            token=token, repo=repo, pr_number=pr_number, label=label_name
        )
    added = target not in current_set
    if added:
        _github_api.add_pr_labels(
            token=token, repo=repo, pr_number=pr_number, labels=[target]
        )

    if to_remove or added:
        print(f"Applied label {target!r} (replaced {sorted(to_remove) or 'nothing'})")
    else:
        print(f"Label {target!r} already set — no changes.")


def _fetch_installation_token(app_id: str, private_key: str, installation_id: str) -> str:
    return _github_app.get_installation_token(
        app_id=app_id,
        private_key_pem=private_key,
        installation_id=installation_id,
    )


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    sys.exit(run())
