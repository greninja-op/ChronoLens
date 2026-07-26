"""WhatsApp Business Cloud API Approve-to-Act Integration for ChronoLens.

Provides Meta Webhook verification, HMAC-SHA256 signature checking, interactive
WhatsApp button approval card posting, and real-time callback execution driving
the PREVENT -> VERIFY -> COOLDOWN -> RECORD closed loop.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any

import httpx

from .config import Config
from .foresee import Forecast

logger = logging.getLogger("chronolens.whatsapp")


# --------------------------------------------------------------------------- #
# HMAC-SHA256 Signature Verification
# --------------------------------------------------------------------------- #
def verify_whatsapp_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    """Validate Meta x-hub-signature-256 header using HMAC-SHA256.

    Fails **closed** whenever a secret is configured: if ``WHATSAPP_APP_SECRET`` is
    set, a missing or mismatched signature is rejected. The only permissive case is
    local development with no secret configured at all (nothing to verify against),
    which is why the webhook must not be exposed publicly without the secret set.
    """
    if not app_secret:
        return True   # dev only: no secret configured, nothing to verify against
    if not signature_header:
        return False  # secret IS configured -> an unsigned request is rejected

    expected_prefix = "sha256="
    if not signature_header.startswith(expected_prefix):
        return False

    received_sig = signature_header[len(expected_prefix):].strip()
    computed_sig = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received_sig.lower(), computed_sig.lower())


# --------------------------------------------------------------------------- #
# Message Senders
# --------------------------------------------------------------------------- #
def _meta_url(cfg: Config) -> str:
    version = cfg.whatsapp_api_version or "v23.0"
    phone_id = cfg.whatsapp_phone_number_id
    return f"https://graph.facebook.com/{version}/{phone_id}/messages"


def send_whatsapp_text(to: str, text: str, cfg: Config) -> dict[str, Any]:
    """Send a plain-text WhatsApp message via Meta Cloud API."""
    if not cfg.whatsapp_enabled():
        return {"ok": False, "error": "WhatsApp credentials not configured"}

    url = _meta_url(cfg)
    headers = {
        "Authorization": f"Bearer {cfg.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.strip().replace("+", ""),
        "type": "text",
        "text": {"body": text[:4000], "preview_url": False},
    }


    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        return {"ok": resp.status_code < 300, "status_code": resp.status_code, "body": resp.json()}
    except Exception as e:
        logger.error(f"WhatsApp sendText failed: {e}")
        return {"ok": False, "error": str(e)}


def post_whatsapp_approval(
    fc: Forecast,
    plan: dict[str, Any],
    cfg: Config,
    *,
    recipient: str | None = None,
    lang: str = "en-IN",
) -> dict[str, Any]:
    """Send an interactive WhatsApp approval card with Approve/Deny buttons (supports Hindi translation)."""
    if not cfg.whatsapp_enabled():
        return {"ok": False, "error": "WhatsApp not enabled"}

    to = recipient or cfg.whatsapp_recipient_number
    action = plan.get("action", "scale_out")
    svc = fc.service

    body_text = (
        f"🛡️ *ChronoLens Approval Required*\n\n"
        f"• *Service*: `{svc}`\n"
        f"• *p99 Latency*: {fc.current_p99_ms:.1f}ms -> SLO wall {cfg.p99_slo_ms}ms\n"
        f"• *Trend Slope*: +{fc.slope_ms_per_s:.1f}ms/s\n"
        f"• *ETA to Breach*: {fc.seconds_to_breach or 0:.1f}s\n"
        f"• *Proposed Action*: `{action}` (+{plan.get('capacity_delta', 1)} unit)\n\n"
        f"Tap *Approve* to execute reversible remediation and verify via SigNoz."
    )

    url = _meta_url(cfg)

    headers = {
        "Authorization": f"Bearer {cfg.whatsapp_token}",
        "Content-Type": "application/json",
    }

    # Meta interactive reply buttons (max 3 buttons, title <= 20 chars)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.strip().replace("+", ""),
        "type": "interactive",
        "interactive": {

            "type": "button",
            "header": {"type": "text", "text": "🛡️ ChronoLens Reliability Guard"},
            "body": {"text": body_text[:1024]},
            "footer": {"text": "SigNoz Closed-Loop SRE Engine"},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"wa_appr:{svc}:{action}",
                            "title": "✅ Approve Fix",
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"wa_deny:{svc}:{action}",
                            "title": "❌ Deny Fix",
                        },
                    },
                ]
            },
        },
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        return {"ok": resp.status_code < 300, "status_code": resp.status_code, "body": resp.json()}
    except Exception as e:
        logger.error(f"WhatsApp post_approval failed: {e}")
        return {"ok": False, "error": str(e)}


def post_whatsapp_agent_approval(
    reason: str,
    detail: str,
    cfg: Config,
    *,
    recipient: str | None = None,
) -> dict[str, Any]:
    """Send an interactive WhatsApp Agent Watch approval card."""
    if not cfg.whatsapp_enabled():
        return {"ok": False, "error": "WhatsApp not enabled"}

    to = recipient or cfg.whatsapp_recipient_number
    body_text = (
        f"🤖 *ChronoLens Agent Watch Guard*\n\n"
        f"• *Issue*: {reason}\n"
        f"• *Detail*: {detail[:300]}\n\n"
        f"Tap *Break/Pin Baseline* to throttle agent context window & pin baseline model."
    )

    url = _meta_url(cfg)
    headers = {
        "Authorization": f"Bearer {cfg.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to.strip().replace("+", ""),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {"type": "text", "text": "🤖 Agent Watch Circuit Breaker"},
            "body": {"text": body_text[:1024]},
            "footer": {"text": "SigNoz GenAI Spans Engine"},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "wa_agent_break",
                            "title": "🛑 Break & Pin",
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "wa_agent_ignore",
                            "title": "Ignore",
                        },
                    },
                ]
            },
        },
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        return {"ok": resp.status_code < 300, "status_code": resp.status_code, "body": resp.json()}
    except Exception as e:
        logger.error(f"WhatsApp post_agent_approval failed: {e}")
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# Webhook Callback Execution
# --------------------------------------------------------------------------- #
def _ack(sender_phone: str, text: str, cfg: Config) -> bool:
    """Reply the instant a button is tapped, before any remediation runs.

    Remediation is a real PREVENT → VERIFY → COOLDOWN cycle and takes tens of
    seconds. Without this the approver taps a button on their phone and gets
    silence, which reads as "the tap didn't register" — so they tap again. One
    immediate acknowledgement removes both the doubt and the double-tap.
    """
    try:
        return bool(send_whatsapp_text(sender_phone, text, cfg).get("ok"))
    except Exception as exc:  # fail open — never block the action on a reply
        logger.error(f"WhatsApp ack failed: {exc}")
        return False


def process_whatsapp_button_click(
    button_id: str,
    sender_phone: str,
    cfg: Config,
) -> dict[str, Any]:
    """Handle a WhatsApp button tap: acknowledge instantly, act, then report back.

    Every branch sends **two** messages — an immediate acknowledgement and a final
    outcome — and routes through the *same* approval engine Slack uses
    (``slack_bot.execute_approved`` and friends), tagged ``surface="whatsapp"`` so
    the ledger receipt records where the decision came from.
    """
    from .slack_bot import (
        execute_agent_break,
        execute_approved,
        record_agent_ignore,
        record_denial,
    )

    button_id = (button_id or "").strip()
    who = f"WhatsApp +{sender_phone}" if sender_phone else "WhatsApp"
    default_service = os.getenv("CHRONOLENS_SERVICE", "chronolens-store")
    agent_service = os.getenv("AGENT_SERVICE_NAME", "chronolens-agent")

    if button_id.startswith("wa_appr:"):
        parts = button_id.split(":")
        svc = parts[1] if len(parts) > 1 else default_service
        action = parts[2] if len(parts) > 2 else "scale_out"
        acked = _ack(sender_phone,
                     f"⏳ *Approved — working on it.*\n\n"
                     f"• *Service*: {svc}\n"
                     f"• *Applying*: {action} (reversible)\n\n"
                     f"I'll message you the SigNoz-verified result in a moment.", cfg)
        try:
            result = execute_approved(cfg, {"service": svc, "action": action},
                                      approver=who, surface="whatsapp")
        except Exception as exc:
            send_whatsapp_text(sender_phone, f"❌ *ChronoLens hit an error*: {exc}", cfg)
            return {"ok": False, "acked": acked, "error": str(exc)}
        send_whatsapp_text(sender_phone, result, cfg)
        return {"ok": True, "acked": acked, "action": "executed", "result": result}

    if button_id.startswith("wa_deny:"):
        parts = button_id.split(":")
        svc = parts[1] if len(parts) > 1 else default_service
        action = parts[2] if len(parts) > 2 else "scale_out"
        acked = _ack(sender_phone, "✋ *Denied — standing down.* Recording your decision…", cfg)
        result = record_denial(cfg, {"service": svc, "action": action},
                               approver=who, surface="whatsapp")
        send_whatsapp_text(sender_phone, result, cfg)
        return {"ok": True, "acked": acked, "action": "denied", "result": result}

    if button_id == "wa_agent_break":
        acked = _ack(sender_phone,
                     "⏳ *Breaking the agent.* Pinning it back to its last-good "
                     "baseline and checking the next turn…", cfg)
        result = execute_agent_break(cfg, {"kind": "loop", "service": agent_service},
                                     approver=who, surface="whatsapp")
        send_whatsapp_text(sender_phone, result, cfg)
        return {"ok": True, "acked": acked, "action": "agent_pinned", "result": result}

    if button_id == "wa_agent_ignore":
        acked = _ack(sender_phone, "ℹ️ *Ignoring.* Recording that you let it ride…", cfg)
        result = record_agent_ignore(cfg, {"kind": "loop", "service": agent_service},
                                     approver=who, surface="whatsapp")
        send_whatsapp_text(sender_phone, result, cfg)
        return {"ok": True, "acked": acked, "action": "agent_ignored", "result": result}

    # Unknown taps still get an answer — silence looks like a broken integration.
    _ack(sender_phone,
         "🤔 I didn't recognise that button. It may belong to an older message — "
         "wait for the next ChronoLens card.", cfg)
    return {"ok": False, "error": f"Unknown button_id '{button_id}'"}
