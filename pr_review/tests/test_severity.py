"""Tests for severity extraction and check-conclusion mapping."""
from __future__ import annotations

import pytest

from pr_review import severity


def test_extract_severity_from_tagged_output():
    text = "Some review text.\n\n<severity>2</severity>\n\nMore text."
    assert severity.extract(text) == 2


def test_extract_severity_zero():
    assert severity.extract("<severity>0</severity>") == 0


def test_extract_severity_three():
    assert severity.extract("<severity>3</severity>") == 3


def test_extract_returns_none_when_missing():
    """When the model fails to emit a severity tag, return None (orchestrator handles fallback)."""
    assert severity.extract("Just a review with no tag.") is None


def test_extract_invalid_severity_returns_none():
    """Out-of-range values are treated as missing — defensive against model malformation."""
    assert severity.extract("<severity>7</severity>") is None
    assert severity.extract("<severity>-1</severity>") is None
    assert severity.extract("<severity>abc</severity>") is None


def test_conclusion_zero_is_success():
    assert severity.to_check_conclusion(0) == "success"


def test_conclusion_one_is_success():
    assert severity.to_check_conclusion(1) == "success"


def test_conclusion_two_is_neutral():
    assert severity.to_check_conclusion(2) == "neutral"


def test_conclusion_three_is_action_required():
    assert severity.to_check_conclusion(3) == "action_required"


def test_conclusion_none_defaults_to_neutral():
    """If severity couldn't be extracted, default to neutral (don't fail-open or fail-closed)."""
    assert severity.to_check_conclusion(None) == "neutral"


def test_conclusion_invalid_raises():
    with pytest.raises(ValueError):
        severity.to_check_conclusion(99)


def test_summary_for_check_run():
    """Short one-line summary used in the check-run output panel."""
    assert "clean" in severity.summary(0).lower()
    assert "nit" in severity.summary(1).lower()
    assert "look" in severity.summary(2).lower()
    assert "blocker" in severity.summary(3).lower() or "fix" in severity.summary(3).lower()
