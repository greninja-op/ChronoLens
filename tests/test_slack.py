"""Unit tests for the Slack approve-to-act helpers (no network)."""
from __future__ import annotations

import json

from chronolens.slack_bot import (
    APPROVE_ACTION,
    DENY_ACTION,
    build_approval_blocks,
)


def _blocks():
    value = json.dumps({"service": "payment", "signal": "pool", "action": "pool-resize"})
    return build_approval_blocks(
        service="payment", signal="pool", action="pool-resize",
        why="connection pool leaking", eta_s=90, p99_ms=420.0,
        confidence=0.82, value=value,
    )


def test_blocks_have_header_and_two_buttons():
    blocks = _blocks()
    assert blocks[0]["type"] == "header"
    actions = [b for b in blocks if b["type"] == "actions"][0]
    ids = {e["action_id"] for e in actions["elements"]}
    assert ids == {APPROVE_ACTION, DENY_ACTION}


def test_button_value_roundtrips_payload():
    blocks = _blocks()
    actions = [b for b in blocks if b["type"] == "actions"][0]
    for el in actions["elements"]:
        payload = json.loads(el["value"])
        assert payload["service"] == "payment"
        assert payload["action"] == "pool-resize"


def test_detail_mentions_service_signal_and_reversible():
    blocks = _blocks()
    section = blocks[1]["text"]["text"]
    assert "payment" in section
    assert "pool" in section
    assert "reversible" in section.lower()
