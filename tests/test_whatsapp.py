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
def test_process_button_click_deny():
    cfg = Config.load()
    res = process_whatsapp_button_click("wa_deny:checkout-service:scale_out", "919400245958", cfg)
    assert res["ok"] is True
    assert res["action"] == "denied"


def test_process_button_click_agent_break():
    cfg = Config.load()
    res = process_whatsapp_button_click("wa_agent_break", "919400245958", cfg)
    assert res["ok"] is True
    assert res["action"] == "agent_pinned"


def test_process_button_click_agent_ignore():
    cfg = Config.load()
    res = process_whatsapp_button_click("wa_agent_ignore", "919400245958", cfg)
    assert res["ok"] is True
    assert res["action"] == "agent_ignored"


def test_process_button_click_unknown():
    cfg = Config.load()
    res = process_whatsapp_button_click("wa_unknown_button", "919400245958", cfg)
    assert res["ok"] is False
    assert "Unknown button_id" in res["error"]
