"""Tests for the review label catalog and severity→label mapping."""
from __future__ import annotations

import pytest

from pr_review import labels


def test_all_review_labels_returns_four_names():
    names = labels.all_review_labels()
    assert set(names) == {
        "review:pending",
        "review:ready",
        "review:nits",
        "review:blocker",
    }


def test_review_labels_have_required_metadata():
    for name, meta in labels.REVIEW_LABELS.items():
        assert "color" in meta
        assert "description" in meta
        assert len(meta["color"]) == 6  # hex without leading #
        assert meta["description"]  # non-empty


def test_severity_to_label_maps_0_and_1_to_ready():
    assert labels.severity_to_label(0) == "review:ready"
    assert labels.severity_to_label(1) == "review:ready"


def test_severity_to_label_maps_2_to_nits():
    assert labels.severity_to_label(2) == "review:nits"


def test_severity_to_label_maps_3_to_blocker():
    assert labels.severity_to_label(3) == "review:blocker"


def test_severity_to_label_falls_back_to_pending_for_none():
    assert labels.severity_to_label(None) == "review:pending"


def test_severity_to_label_falls_back_to_pending_for_invalid():
    # -1, 4, 99 → not in 0..3 range → pending
    assert labels.severity_to_label(-1) == "review:pending"
    assert labels.severity_to_label(4) == "review:pending"


def test_is_review_label_true_for_known_labels():
    assert labels.is_review_label("review:ready") is True
    assert labels.is_review_label("review:blocker") is True


def test_is_review_label_false_for_other_labels():
    assert labels.is_review_label("wip") is False
    assert labels.is_review_label("type: bug") is False
    assert labels.is_review_label("") is False


def test_suppress_labels_set():
    assert labels.SUPPRESS_LABELS == {"wip", "no-pr-watch"}
