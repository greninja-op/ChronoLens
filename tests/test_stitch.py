"""Unit & Property-based tests for Stitch AI Integration in ChronoLens:

- Event Stream Payload Envelope Construction
- Inbound Webhook Processing (trigger_loop & get_forecast)
- Authorization & Workspace Headers
"""
from __future__ import annotations

import os
import sys
from hypothesis import given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chronolens.config import Config
from chronolens.stitch import process_stitch_webhook, stream_event_to_stitch


def test_stitch_event_streaming_structure():
    cfg = Config.load()
    payload = {
        "service": "checkout-service",
        "p99_ms": 480.0,
        "slope_ms_per_s": 18.5,
        "action": "scale_out",
    }
    res = stream_event_to_stitch("test_incident", payload, cfg)
    assert isinstance(res, dict)
    assert "ok" in res
    assert res["event_type"] == "test_incident"


@settings(deadline=None)
@given(event_name=st.text(min_size=1, max_size=50))
def test_stitch_event_property(event_name: str):
    cfg = Config.load()
    res = stream_event_to_stitch(event_name, {"test": True}, cfg)
    assert isinstance(res, dict)
    assert "ok" in res


def test_stitch_webhook_get_forecast():
    cfg = Config.load()
    body = {"action": "get_forecast"}
    res = process_stitch_webhook(body, cfg)
    assert res["ok"] is True
    assert res["action"] == "get_forecast"
    assert "service" in res


def test_stitch_webhook_unknown_action():
    cfg = Config.load()
    body = {"action": "custom_sync"}
    res = process_stitch_webhook(body, cfg)
    assert res["ok"] is True
    assert res["action"] == "custom_sync"
