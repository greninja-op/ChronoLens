"""Unit tests for the live quality judge (rule-based grader)."""
from __future__ import annotations

from chronolens.judge import grade_batch, rule_based, score_response

GOOD = "Sure — one latte and one croissant, that's $7.50. Anything else?"
HEDGY = "I'm still checking the menu... let me look again... I'm not sure I found it yet..."
RAMBLING = "Absolutely! " + ("I would be delighted to help you in great detail. " * 12)


def test_good_answer_scores_high():
    q = rule_based(GOOD)
    assert q.verdict == "good" and q.score >= 0.7


def test_hedging_answer_is_degraded_or_bad():
    q = rule_based(HEDGY)
    assert q.verdict in ("degraded", "bad")
    assert any("hedging" in r for r in q.reasons)


def test_rambling_answer_is_penalized():
    q = rule_based(RAMBLING, baseline_len=160)
    assert q.score < 1.0 and any("rambling" in r or "long" in r for r in q.reasons)


def test_score_response_defaults_to_rule_based_without_llm():
    class Cfg:
        llm_provider = "none"
    q = score_response(GOOD, Cfg())
    assert q.source == "rule-based" and q.verdict == "good"


def test_grade_batch_trends_quality():
    res = grade_batch([GOOD, GOOD, HEDGY])
    assert res["n"] == 3
    assert 0.0 <= res["avg_score"] <= 1.0
    assert res["degraded_pct"] >= 33  # at least the hedgy one flagged
