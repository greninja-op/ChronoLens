"""Slack two-way approve-to-act — the human end of the trust ladder.

When GOVERN decides ChronoLens may *not* act on its own (autonomy ``suggest``, or
``earn`` before trust is earned), it posts an **interactive approval** to Slack:
the forecast, the dominant signal, and the proposed *reversible* action, with
**Approve / Deny** buttons. A human taps Approve and ChronoLens executes the real
PREVENT → VERIFY → COOLDOWN → RECORD path, then edits the message with the
SigNoz-verified outcome. Taps Deny and it records the decision and stands down.

Design notes:
- **Socket Mode** (an outbound WebSocket) means no public URL — ideal for local
  demos. The bot token (``xoxb-``) posts/reads; the app token (``xapp-``) opens
  the socket.
- The button ``value`` carries the whole action spec, so the click handler can
  act with no shared database — everything it needs travels with the message.
- Fails open everywhere: if the Slack SDK isn't installed or tokens are unset,
  every function no-ops and the loop is unaffected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .config import Config

APPROVE_ACTION = "chronolens_approve"
DENY_ACTION = "chronolens_deny"


@dataclass
class PostResult:
    ok: bool
    ts: str = ""
    reason: str = ""


def _signal_emoji(signal: str) -> str:
    return {
        "load": "📈", "dependency": "🔗", "pool": "🕳️",
        "memory": "🧠", "errors": "💥",
    }.get(signal, "⚠️")


def build_approval_blocks(*, service: str, signal: str, action: str, why: str,
                          eta_s: float | None, p99_ms: float, confidence: float,
                          value: str) -> list[dict]:
    """Compose the Block Kit payload for an approval request (pure — no network)."""
    when = "now" if not eta_s else f"in ~{eta_s:.0f}s"
    header = f"{_signal_emoji(signal)} ChronoLens needs your approval"
    detail = (
        f"*Service:* `{service}`\n"
        f"*Forecast:* p99 heading past SLO *{when}*  (confidence {confidence:.0%})\n"
        f"*Current p99:* {p99_ms:.0f} ms\n"
        f"*Signal:* {signal}\n"
        f"*Proposed fix:* `{action}` — _reversible_\n"
        f"*Why:* {why}"
    )
    return [
        {"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": detail}},
        {"type": "actions", "block_id": "chronolens_decision", "elements": [
            {"type": "button", "action_id": APPROVE_ACTION, "style": "primary",
             "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True}, "value": value},
            {"type": "button", "action_id": DENY_ACTION, "style": "danger",
             "text": {"type": "plain_text", "text": "✋ Deny", "emoji": True}, "value": value},
        ]},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": "ChronoLens · reversible action · verified via SigNoz"}]},
    ]


def _encode(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _web_client(cfg: Config):
    """Lazily build a slack_sdk WebClient; returns None if unavailable."""
    if not cfg.slack_bot_token:
        return None
    try:
        from slack_sdk import WebClient
    except Exception:
        return None
    return WebClient(token=cfg.slack_bot_token)


def post_text(cfg: Config, text: str) -> PostResult:
    """Post a plain message to the configured channel. Never raises."""
    client = _web_client(cfg)
    if client is None:
        return PostResult(False, reason="slack not configured / sdk missing")
    try:
        resp = client.chat_postMessage(channel=cfg.slack_channel, text=text)
        return PostResult(bool(resp.get("ok")), ts=resp.get("ts", ""))
    except Exception as exc:  # fail open
        return PostResult(False, reason=f"post failed: {exc}")


def post_approval(cfg: Config, *, service: str, signal: str, action: str, why: str,
                  eta_s: float | None, p99_ms: float, confidence: float,
                  slo_ms: float) -> PostResult:
    """Post an interactive approval request for a suggested action. Never raises."""
    client = _web_client(cfg)
    if client is None:
        return PostResult(False, reason="slack not configured / sdk missing")
    value = _encode({"service": service, "signal": signal, "action": action,
                     "why": why, "eta_s": eta_s, "p99_ms": p99_ms,
                     "confidence": confidence, "slo_ms": slo_ms})
    blocks = build_approval_blocks(service=service, signal=signal, action=action,
                                   why=why, eta_s=eta_s, p99_ms=p99_ms,
                                   confidence=confidence, value=value)
    try:
        resp = client.chat_postMessage(
            channel=cfg.slack_channel, blocks=blocks,
            text=f"ChronoLens: approve '{action}' on {service}?")
        return PostResult(bool(resp.get("ok")), ts=resp.get("ts", ""))
    except Exception as exc:  # fail open
        return PostResult(False, reason=f"post failed: {exc}")


# --------------------------------------------------------------------------- #
# Execute an approved action: the real PREVENT → VERIFY → COOLDOWN → RECORD.   #
# --------------------------------------------------------------------------- #
def execute_approved(cfg: Config, payload: dict, *, approver: str = "a teammate") -> str:
    """Run the reversible action a human approved, verify it, and record it.

    Mirrors the loop's may-act path (minus the SigNoz guard/silence extras) so a
    Slack approval drives the *same* remediation code the autonomous loop uses.
    Returns a short human-readable outcome line for the Slack message.
    """
    from .cooldown import cool_down
    from .dollars import units_to_dollars
    from .notify import build_message, notify
    from .prevent import apply, propose, rollback
    from .record import Ledger, new_case
    from .signoz import SigNozClient
    from .verify import verify

    service = payload.get("service", "?")
    signal = payload.get("signal")
    p99_at = float(payload.get("p99_ms", 0.0) or 0.0)
    eta_s = payload.get("eta_s")
    confidence = float(payload.get("confidence", 1.0) or 1.0)

    rem = propose(service, cfg, signal=signal)
    ledger = Ledger()

    with SigNozClient(cfg) as sn:
        rem = apply(cfg, rem)
        if rem.blocked:
            _record(ledger, new_case, service, cfg, p99_at, eta_s, rem,
                    verified=False, final=p99_at, peak=p99_at, outcome="held",
                    confidence=confidence, dollars=0.0, approver=approver)
            return f"✋ Held by guardrails — {rem.block_reason}. No change made."
        if not rem.applied:
            return f"⚠️ Couldn't apply `{rem.action}` on {service}: {rem.error or 'unknown error'}."

        v = verify(sn, service, cfg.p99_slo_ms)
        if v.verified:
            cd = cool_down(cfg)
            dollars = units_to_dollars(cd.cost_units_returned, cfg) if cd else 0.0
            _record(ledger, new_case, service, cfg, p99_at, eta_s, rem,
                    verified=True, final=v.final_p99_ms, peak=v.peak_p99_ms,
                    outcome="breach avoided", confidence=confidence,
                    dollars=dollars, approver=approver, cooldown=cd)
            msg = build_message(service=service, outcome="breach avoided",
                                action=rem.action, eta_s=eta_s, p99_before=p99_at,
                                p99_after=v.final_p99_ms, dollars_saved=dollars)
            notify(cfg, msg, sn=sn)
            extra = f" · returned ~${dollars:,.2f}" if dollars > 0 else ""
            return (f"✅ Approved by {approver}. Applied `{rem.action}` → SigNoz confirms "
                    f"p99 back to {v.final_p99_ms:.0f} ms — *breach avoided*{extra}. "
                    f"Rollback available: {rem.rollback}.")
        # verify failed → undo
        rolled = rollback(cfg, rem)
        _record(ledger, new_case, service, cfg, p99_at, eta_s, rem,
                verified=False, final=v.final_p99_ms, peak=v.peak_p99_ms,
                outcome="escalated", confidence=confidence, dollars=0.0, approver=approver)
        return (f"🚨 Applied `{rem.action}` but p99 didn't recover ({v.final_p99_ms:.0f} ms). "
                f"{'Rolled back. ' if rolled else ''}Escalating to a human.")


def _record(ledger, new_case, service, cfg, p99_at, eta_s, rem, *, verified,
            final, peak, outcome, confidence, dollars, approver, cooldown=None):
    """File a case for a Slack-approved decision (LEARN's memory next time)."""
    case = new_case(
        service=service, predicted_breach_in_s=eta_s, p99_at_prediction_ms=p99_at,
        slo_ms=cfg.p99_slo_ms, action=rem.action, rollback=rem.rollback,
        verified=verified, final_p99_ms=final, peak_p99_ms=peak, outcome=outcome,
        signal=rem.signal, why=rem.why, confidence=confidence,
        autonomy_mode=cfg.autonomy, dollars_saved=dollars,
        scaled_down=bool(cooldown and cooldown.scaled_down),
        cost_units_returned=cooldown.cost_units_returned if cooldown else 0.0,
        explanation=f"Approved via Slack by {approver}.",
        explanation_source="slack-approval",
        evidence={"approved_via": "slack", "approver": approver},
    )
    ledger.record(case)


def record_denial(cfg: Config, payload: dict, *, approver: str = "a teammate") -> str:
    """Record that a human declined the suggested action."""
    from .record import Ledger, new_case
    service = payload.get("service", "?")
    ledger = Ledger()
    case = new_case(
        service=service, predicted_breach_in_s=payload.get("eta_s"),
        p99_at_prediction_ms=float(payload.get("p99_ms", 0.0) or 0.0),
        slo_ms=cfg.p99_slo_ms, action="none",
        rollback="", verified=False, final_p99_ms=float(payload.get("p99_ms", 0.0) or 0.0),
        peak_p99_ms=float(payload.get("p99_ms", 0.0) or 0.0), outcome="declined",
        signal=payload.get("signal", "load"), why=payload.get("why", ""),
        confidence=float(payload.get("confidence", 1.0) or 1.0),
        autonomy_mode=cfg.autonomy,
        explanation=f"Suggested `{payload.get('action')}` declined via Slack by {approver}.",
        explanation_source="slack-approval",
        evidence={"approved_via": "slack", "approver": approver, "decision": "deny"},
    )
    ledger.record(case)
    return f"✋ Declined by {approver}. ChronoLens stood down — no action taken on {service}."


# --------------------------------------------------------------------------- #
# The Socket Mode listener: turns button clicks into real remediation.        #
# --------------------------------------------------------------------------- #
def run_listener(cfg: Config) -> None:
    """Start the Socket Mode listener (blocks). Requires slack_bolt + tokens."""
    if not cfg.slack_enabled():
        raise RuntimeError(
            "Slack not configured — set SLACK_BOT_TOKEN (xoxb-…) and "
            "SLACK_APP_TOKEN (xapp-…) in .env.")
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "slack_bolt not installed. Run: pip install slack_bolt slack_sdk") from exc

    app = App(token=cfg.slack_bot_token)

    def _approver_name(body) -> str:
        try:
            return "<@%s>" % body["user"]["id"]
        except Exception:
            return "a teammate"

    @app.action(APPROVE_ACTION)
    def _on_approve(ack, body, client, action, logger):  # noqa: ANN001
        ack()
        payload = json.loads(action["value"])
        who = _approver_name(body)
        ch = body["channel"]["id"]
        ts = body["message"]["ts"]
        try:
            client.chat_update(channel=ch, ts=ts,
                               text=f"⏳ Applying `{payload.get('action')}` on "
                                    f"{payload.get('service')} (approved by {who})…",
                               blocks=[])
        except Exception:
            pass
        result = execute_approved(cfg, payload, approver=who)
        try:
            client.chat_update(channel=ch, ts=ts, text=result, blocks=[])
        except Exception:
            client.chat_postMessage(channel=ch, text=result)

    @app.action(DENY_ACTION)
    def _on_deny(ack, body, client, action, logger):  # noqa: ANN001
        ack()
        payload = json.loads(action["value"])
        who = _approver_name(body)
        result = record_denial(cfg, payload, approver=who)
        try:
            client.chat_update(channel=body["channel"]["id"],
                               ts=body["message"]["ts"], text=result, blocks=[])
        except Exception:
            pass

    print(f"ChronoLens Slack listener online — posting approvals to {cfg.slack_channel}. "
          f"Ctrl+C to stop.")
    SocketModeHandler(app, cfg.slack_app_token).start()
