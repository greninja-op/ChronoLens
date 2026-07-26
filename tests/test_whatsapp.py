"""Unit & Property-based tests for WhatsApp Business Cloud API Integration in ChronoLens:

- HMAC SHA-256 Signature Verification
- Interactive Approval Card Construction (Meta Graph API schema)
- Inbound Webhook Button Click Processing
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys

import pytest
from hypothesis import given, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chronolens.config import Config
from chronolens.foresee import Forecast
from chronolens.whatsapp_bot import (
    post_whatsapp_agent_approval,
    post_whatsapp_approval,
    process_whatsapp_button_click,
    send_whatsapp_text,
    verify_whatsapp_signature,
)


# --------------------------------------------------------------------------- #
# 1. HMAC-SHA256 Signature Verification Tests
# --------------------------------------------------------------------------- #
def test_signature_verification_valid():
    secret = "6ba41a4a98cd751c83c4a53a2d1d11a0"
    body = b'{"object":"whatsapp_business_account","entry":[]}'
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    assert verify_whatsapp_signature(body, sig, secret) is True


def test_signature_verification_tampered():
    secret = "6ba41a4a98cd751c83c4a53a2d1d11a0"
    body = b'{"object":"whatsapp_business_account","entry":[]}'
    tampered_body = b'{"object":"whatsapp_business_account","entry":[{"tampered":true}]}'
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    assert verify_whatsapp_signature(tampered_body, sig, secret) is False
    assert verify_whatsapp_signature(body, "invalid_sig", secret) is False


@given(payload=st.binary(min_size=1, max_size=500), secret=st.text(min_size=1, max_size=32))
def test_signature_property(payload: bytes, secret: str):
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert verify_whatsapp_signature(payload, sig, secret) is True
    assert verify_whatsapp_signature(payload + b"x", sig, secret) is False


# --------------------------------------------------------------------------- #
# 2. Interactive Card Formatting Tests
# --------------------------------------------------------------------------- #
def test_post_whatsapp_approval_structure():
    cfg = Config.load()
    fc = Forecast(
        service="checkout-service",
        current_p99_ms=480.0,
        slope_ms_per_s=18.5,
        seconds_to_breach=18.2,
        breaching_now=False,
        confidence=0.92,
        confident=True,
    )
    plan = {"action": "scale_out", "capacity_delta": 1}
    res = post_whatsapp_approval(fc, plan, cfg, recipient="919400245958")
    assert isinstance(res, dict)
    assert "ok" in res


def test_post_whatsapp_agent_approval_structure():
    cfg = Config.load()
    res = post_whatsapp_agent_approval("Runaway tool loop", "Tool search_store repeated 12x", cfg)
    assert isinstance(res, dict)
    assert "ok" in res


# --------------------------------------------------------------------------- #
# 3. Webhook Button Click Processing Tests
# --------------------------------------------------------------------------- #
@pytest.fixture()
def sent(monkeypatch):
    """Capture outbound WhatsApp messages and stub the remediation engine.

    The engine is the *shared* one in ``slack_bot`` — stubbing it here keeps these
    tests about the WhatsApp reply contract, not about remediation.
    """
    import chronolens.slack_bot as sb
    import chronolens.whatsapp_bot as wb

    outbox: list[str] = []
    monkeypatch.setattr(wb, "send_whatsapp_text",
                        lambda to, text, cfg: outbox.append(text) or {"ok": True})
    monkeypatch.setattr(sb, "execute_approved",
                        lambda cfg, p, **kw: "✅ done — breach avoided")
    monkeypatch.setattr(sb, "record_denial", lambda cfg, p, **kw: "✋ declined, recorded")
    monkeypatch.setattr(sb, "execute_agent_break", lambda cfg, p, **kw: "✅ pinned to baseline")
    monkeypatch.setattr(sb, "record_agent_ignore", lambda cfg, p, **kw: "✋ ignored, recorded")
    return outbox


# Every tap must produce an immediate acknowledgement *and* a final outcome, in
# that order. Regression origin: approve used to run a 60s+ remediation in silence,
# so the approver couldn't tell the tap had registered.
@pytest.mark.parametrize("button,expect_action,ack_contains", [
    ("wa_appr:chronolens-store:scale_out", "executed", "working on it"),
    ("wa_deny:chronolens-store:scale_out", "denied", "standing down"),
    ("wa_agent_break", "agent_pinned", "Breaking the agent"),
    ("wa_agent_ignore", "agent_ignored", "Ignoring"),
])
def test_every_button_acks_immediately_then_reports(sent, button, expect_action, ack_contains):
    res = process_whatsapp_button_click(button, "919400245958", Config.load())
    assert res["ok"] is True
    assert res["action"] == expect_action
    assert len(sent) == 2, "expected an immediate ack plus a final outcome"
    assert ack_contains.lower() in sent[0].lower()
    assert sent[1] == res["result"]


def test_process_button_click_unknown_still_replies(sent):
    res = process_whatsapp_button_click("wa_unknown_button", "919400245958", Config.load())
    assert res["ok"] is False
    assert "Unknown button_id" in res["error"]
    assert len(sent) == 1 and "didn't recognise" in sent[0]


def test_approval_records_the_whatsapp_surface(monkeypatch):
    """The ledger receipt must say the decision arrived on WhatsApp, not Slack."""
    import chronolens.slack_bot as sb
    import chronolens.whatsapp_bot as wb

    seen: dict = {}
    monkeypatch.setattr(wb, "send_whatsapp_text", lambda to, text, cfg: {"ok": True})
    monkeypatch.setattr(sb, "execute_approved",
                        lambda cfg, p, **kw: seen.update(kw) or "ok")
    process_whatsapp_button_click("wa_appr:svc:scale_out", "919400245958", Config.load())
    assert seen["surface"] == "whatsapp"
    assert "WhatsApp" in seen["approver"]
