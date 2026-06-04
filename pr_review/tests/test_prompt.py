"""Tests for prompt construction."""
from __future__ import annotations

import re

from pr_review import prompt


def test_build_messages_returns_list_of_dicts():
    result = prompt.build(
        diff="--- a/foo\n+++ b/foo\n@@ -1 +1 @@\n-old\n+new\n",
        tier="a",
        ci_state="green",
        first_run=False,
        pr_title="Test PR",
        pr_body="Test description",
    )
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"


def test_tier_substituted_in_system_prompt():
    result = prompt.build(
        diff="diff",
        tier="b",
        ci_state="green",
        first_run=False,
        pr_title="Test",
        pr_body="",
    )
    system = result[0]["content"]
    assert "**b**" in system or "Tier B" in system
    assert "{{tier}}" not in system


def test_first_run_note_present_when_first_run_true():
    result = prompt.build(
        diff="diff",
        tier="a",
        ci_state="failing",
        first_run=True,
        pr_title="Test",
        pr_body="",
    )
    system = result[0]["content"]
    assert "first" in system.lower() or "discovery" in system.lower()
    assert "{{first_run_note}}" not in system


def test_first_run_note_empty_when_first_run_false():
    result = prompt.build(
        diff="diff",
        tier="a",
        ci_state="green",
        first_run=False,
        pr_title="Test",
        pr_body="",
    )
    system = result[0]["content"]
    assert "{{first_run_note}}" not in system


def test_ci_state_substituted():
    result = prompt.build(
        diff="diff",
        tier="a",
        ci_state="failing",
        first_run=False,
        pr_title="Test",
        pr_body="",
    )
    system = result[0]["content"]
    assert "failing" in system.lower()
    assert "{{ci_state}}" not in system


def test_diff_in_user_message():
    diff = "--- a/foo\n+++ b/foo\n@@ -1 +1 @@\n-old\n+new\n"
    result = prompt.build(
        diff=diff,
        tier="a",
        ci_state="green",
        first_run=False,
        pr_title="Title here",
        pr_body="Description here",
    )
    user = result[1]["content"]
    assert diff in user
    assert "Title here" in user
    assert "Description here" in user


def test_no_unreplaced_placeholders():
    """Every {{...}} in the template must be replaced."""
    result = prompt.build(
        diff="diff",
        tier="a",
        ci_state="green",
        first_run=False,
        pr_title="t",
        pr_body="b",
    )
    for message in result:
        assert not re.search(r"\{\{[^}]+\}\}", message["content"]), \
            f"Unreplaced placeholder in: {message['content'][:200]}"
