"""Unit tests for the agent behavior-drift detector."""
from __future__ import annotations

from chronolens.drift import (
    drift_score,
    fingerprint,
    load_baseline,
    save_baseline,
)


def _normal(n=8):
    return [{"model": "gpt-4o-mini", "tools": ["get_menu", "place_order"],
             "steps": 2, "output_tokens": 150} for _ in range(n)]


def _drifted(n=8):
    # model swapped, a NEW tool appears, answers much longer
    return [{"model": "gpt-4o", "tools": ["web_search", "get_menu", "place_order"],
             "steps": 3, "output_tokens": 500} for _ in range(n)]


def test_same_behavior_is_no_drift():
    base = fingerprint(_normal())
    recent = fingerprint(_normal())
    d = drift_score(base, recent, threshold=0.35)
    assert not d.drifted and d.score < 0.1


def test_model_swap_and_new_tool_is_drift():
    d = drift_score(fingerprint(_normal()), fingerprint(_drifted()), threshold=0.35)
    assert d.drifted and d.score >= 0.35
    joined = " ".join(d.changes)
    assert "web_search" in joined            # new tool called out
    assert "model mix" in joined             # model swap called out
    assert "answer length" in joined         # longer answers called out


def test_fingerprint_normalizes_distributions():
    fp = fingerprint(_normal())
    assert abs(sum(fp.tool_freq.values()) - 1.0) < 1e-9
    assert fp.avg_steps == 2 and fp.avg_tokens == 150


def test_baseline_round_trips(tmp_path):
    fp = fingerprint(_normal())
    save_baseline(fp, root=str(tmp_path))
    loaded = load_baseline(root=str(tmp_path))
    assert loaded is not None
    assert loaded.tool_freq == fp.tool_freq and loaded.avg_tokens == fp.avg_tokens


def test_no_baseline_returns_none(tmp_path):
    assert load_baseline(root=str(tmp_path)) is None
