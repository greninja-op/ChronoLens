"""Unit tests for the loop-control features: precise rollbacks, the action
budget, the global kill switch, and the concurrency lock. No Hypothesis here,
so these run even on hosts that block its native extension.
"""
from __future__ import annotations

import chronolens.prevent as prev
from chronolens.guardrails import FlapGuard
from chronolens.locking import LoopLock
from chronolens.prevent import Remediation


class Cfg:
    def __init__(self, **kw):
        self.demo_store_url = "http://localhost:8090"
        self.min_dwell_s = kw.get("min_dwell_s", 0.0)
        self.max_capacity = kw.get("max_capacity", 12.0)
        self.max_actions_per_hour = kw.get("max_actions_per_hour", 12)


# --------------------------------------------------------------------------- #
# precise rollbacks
# --------------------------------------------------------------------------- #
def _capture(monkeypatch):
    calls = []

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {}

    def _post(url, params=None, timeout=None):
        calls.append(params)
        return _Resp()

    monkeypatch.setattr(prev.httpx, "post", _post)
    return calls


def test_rollback_scale_uses_negative_delta(monkeypatch):
    calls = _capture(monkeypatch)
    rem = Remediation(action="scale", params={"service": "s", "value": 2.0},
                      rollback="", applied=True)
    assert prev.rollback(Cfg(), rem) is True
    assert calls[-1]["action"] == "scale" and calls[-1]["value"] == -2.0


def test_rollback_circuit_break_closes_circuit(monkeypatch):
    calls = _capture(monkeypatch)
    rem = Remediation(action="circuit-break", params={"service": "s", "value": 0.0},
                      rollback="", applied=True)
    assert prev.rollback(Cfg(), rem) is True
    assert calls[-1]["action"] == "close-circuit"


def test_rollback_deploy_redeploys(monkeypatch):
    calls = _capture(monkeypatch)
    rem = Remediation(action="rollback", params={"service": "s", "value": 0.0},
                      rollback="", applied=True)
    assert prev.rollback(Cfg(), rem) is True
    assert calls[-1]["action"] == "redeploy"


def test_rollback_restart_is_noop(monkeypatch):
    calls = _capture(monkeypatch)
    rem = Remediation(action="restart", params={"service": "s"}, rollback="", applied=True)
    assert prev.rollback(Cfg(), rem) is False
    assert calls == []


def test_rollback_skips_when_not_applied(monkeypatch):
    calls = _capture(monkeypatch)
    rem = Remediation(action="scale", params={"value": 2.0}, rollback="", applied=False)
    assert prev.rollback(Cfg(), rem) is False
    assert calls == []


# --------------------------------------------------------------------------- #
# action budget
# --------------------------------------------------------------------------- #
def test_action_budget_blocks_after_max(tmp_path):
    g = FlapGuard(root=str(tmp_path))
    for _ in range(3):
        g.note_action("svc", "scale")
    v = g.check("svc", "scale", min_dwell_s=0, current_capacity=2, scale_value=2,
                max_capacity=12, max_per_hour=3)
    assert not v.allowed and "budget" in v.reason


def test_action_budget_allows_under_max(tmp_path):
    g = FlapGuard(root=str(tmp_path))
    g.note_action("svc", "scale")
    v = g.check("svc", "scale", min_dwell_s=0, current_capacity=2, scale_value=2,
                max_capacity=12, max_per_hour=5)
    assert v.allowed


# --------------------------------------------------------------------------- #
# concurrency lock
# --------------------------------------------------------------------------- #
def test_lock_is_exclusive_and_releasable(tmp_path):
    a = LoopLock(str(tmp_path))
    b = LoopLock(str(tmp_path))
    assert a.acquire() is True
    assert b.acquire() is False        # someone already holds it
    a.release()
    assert b.acquire() is True         # freed -> next run can take it
    b.release()


def test_lock_steals_stale(tmp_path):
    a = LoopLock(str(tmp_path), stale_s=0.0)  # everything is instantly stale
    assert a.acquire() is True
    b = LoopLock(str(tmp_path), stale_s=0.0)
    assert b.acquire() is True         # stale lock gets reclaimed
    b.release()


# --------------------------------------------------------------------------- #
# global kill switch (via run_loop)
# --------------------------------------------------------------------------- #
class KCfg:
    def __init__(self, enabled):
        self.enabled = enabled
        self.autonomy = "auto"
        self.p99_slo_ms = 500.0
        self.llm_provider = "none"
        self.openai_api_key = ""
        self.notify_webhook_url = ""
        self.cost_per_unit_hr = 0.65
        self.trust_min_saves = 3
        self.min_samples = 4
        self.min_slope_ms_per_s = 3.0
        self.demo_store_url = "http://localhost:8090"


def test_kill_switch_observes_only(tmp_path, monkeypatch):
    from chronolens import loop as loop_mod
    from chronolens.foresee import Forecast
    from chronolens.learn import Memory
    from chronolens.record import Ledger

    fc = Forecast("svc", 420.0, 15.0, 8.0, False, [300.0, 360.0, 420.0],
                  confidence=0.9, confident=True)
    monkeypatch.setattr(loop_mod, "worst_service", lambda sn, cfg, **k: fc)
    monkeypatch.setattr(loop_mod, "recall", lambda svc, ledger: Memory(svc, 0, 0, 0.0, 120.0, "first"))
    monkeypatch.setattr(loop_mod, "propose", lambda svc, cfg=None, **k: Remediation(
        action="scale", params={"service": svc, "value": 2.0}, rollback="down",
        signal="load", why="load rising"))
    monkeypatch.setattr(loop_mod, "predict_blast_path",
                        lambda entry, breakdown=None: type("B", (), {
                            "narrative": "n", "root": "db", "source": "topology"})())
    applied = {"n": 0}
    monkeypatch.setattr(loop_mod, "apply",
                        lambda cfg, rem: (applied.__setitem__("n", applied["n"] + 1) or rem))

    class SN:  # all extra reads go through _safe and fail open
        def create_alert(self, r): return {}
        def create_dashboard(self, d): return {}

    res = loop_mod.run_loop(SN(), KCfg(enabled=False), managed=True,
                            ledger=Ledger(root=str(tmp_path)))
    assert res["outcome"] == "disabled"
    assert applied["n"] == 0  # kill switch means PREVENT never fired
