"""Tests for reading agent response text back out of SigNoz logs.

This is what makes answer-quality grading telemetry-driven instead of re-driving
the agent, so the parser has to survive the shape variations SigNoz v5 returns.
"""
from __future__ import annotations

from chronolens.signoz import _log_bodies


def test_reads_bodies_from_v5_raw_rows():
    resp = {"data": {"results": [{"rows": [
        {"data": {"body": "one latte, that's $3.50"}},
        {"data": {"body": "we open at 7am"}},
    ]}]}}
    assert _log_bodies(resp) == ["one latte, that's $3.50", "we open at 7am"]


def test_prefers_explicit_full_text_attribute_over_body():
    """`gen_ai.response.text` is the untruncated field — it must win."""
    resp = {"data": {"results": [{"rows": [
        {"data": {"body": "truncated…", "gen_ai.response.text": "the full answer"}},
    ]}]}}
    assert _log_bodies(resp) == ["the full answer"]


def test_reads_full_text_from_nested_attributes():
    resp = {"data": {"results": [{"rows": [
        {"data": {"attributes": {"gen_ai.response.text": "nested full answer"}}},
    ]}]}}
    assert _log_bodies(resp) == ["nested full answer"]


def test_respects_the_limit():
    rows = [{"data": {"body": f"answer {i}"}} for i in range(10)]
    resp = {"data": {"results": [{"rows": rows}]}}
    assert len(_log_bodies(resp, limit=3)) == 3


def test_blank_and_missing_bodies_are_skipped():
    resp = {"data": {"results": [{"rows": [
        {"data": {"body": "   "}},
        {"data": {"severity_text": "INFO"}},
        {"data": {"body": "real answer"}},
    ]}]}}
    assert _log_bodies(resp) == ["real answer"]


def test_empty_or_unexpected_shape_returns_empty_not_error():
    assert _log_bodies({}) == []
    assert _log_bodies({"data": None}) == []
    assert _log_bodies({"data": {"results": []}}) == []
    assert _log_bodies({"data": {"weird": {"nope": 1}}}) == []
