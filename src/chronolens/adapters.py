"""Remediation adapters — where a reversible action actually lands.

The loop decides *what* to do (scale / circuit-break / restart / rollback…) and
the adapter decides *how* to make it happen on a real target. The demo store is
the default; the same reversible-action interface also maps onto Kubernetes and
a generic shell escape hatch, so ChronoLens isn't wedded to the simulation.

    CHRONOLENS_ADAPTER = demo | kubernetes | shell

Only the demo adapter is exercised in this repo's tests; the k8s and shell
adapters are real code but assume a cluster / configured commands to act on.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass

import httpx

from .config import Config


@dataclass
class ActionResult:
    ok: bool
    detail: str


class Adapter:
    def apply(self, action: str, service: str, value: float) -> ActionResult:  # pragma: no cover
        raise NotImplementedError

    def rollback(self, action: str, service: str, value: float) -> bool:  # pragma: no cover
        raise NotImplementedError


class DemoStoreAdapter(Adapter):
    """Pulls the demo store's admin levers over HTTP (the default demo target)."""

    def __init__(self, cfg: Config):
        self.base = cfg.demo_store_url

    def _lever(self, action: str, value: float) -> dict:
        r = httpx.post(f"{self.base}/admin/lever",
                       params={"action": action, "value": value}, timeout=8)
        r.raise_for_status()
        return r.json()

    def apply(self, action: str, service: str, value: float) -> ActionResult:
        try:
            return ActionResult(True, str(self._lever(action, value)))
        except Exception as exc:
            return ActionResult(False, f"demo lever failed: {exc}")

    _INVERSE = {"scale": ("scale", -1), "pool-resize": ("pool-resize", -1),
                "circuit-break": ("close-circuit", 0), "rollback": ("redeploy", 0)}

    def rollback(self, action: str, service: str, value: float) -> bool:
        inv = self._INVERSE.get(action)
        if not inv:
            return False
        try:
            self._lever(inv[0], value * inv[1])
            return True
        except Exception:
            return False


class KubernetesAdapter(Adapter):
    """Maps reversible actions onto kubectl (assumes a reachable cluster/context).

    scale        → kubectl scale deployment/<svc> --replicas=<current±delta>
    restart      → kubectl rollout restart deployment/<svc>
    rollback     → kubectl rollout undo deployment/<svc>
    others       → no-op with a note (not generically mappable)
    """

    def __init__(self, cfg: Config):
        self.ns = os.getenv("CHRONOLENS_K8S_NAMESPACE", "default")

    def _kubectl(self, *args: str) -> str:
        out = subprocess.run(["kubectl", "-n", self.ns, *args],
                             capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or "kubectl failed")
        return out.stdout.strip()

    def _replicas(self, service: str) -> int:
        return int(self._kubectl("get", "deployment", service,
                                 "-o", "jsonpath={.spec.replicas}") or "1")

    def apply(self, action: str, service: str, value: float) -> ActionResult:
        try:
            if action in ("scale", "pool-resize"):
                target = max(1, self._replicas(service) + int(value))
                self._kubectl("scale", f"deployment/{service}", f"--replicas={target}")
                return ActionResult(True, f"scaled {service} to {target} replicas")
            if action == "restart":
                self._kubectl("rollout", "restart", f"deployment/{service}")
                return ActionResult(True, f"rolling-restarted {service}")
            if action == "rollback":
                self._kubectl("rollout", "undo", f"deployment/{service}")
                return ActionResult(True, f"rolled back {service}")
            return ActionResult(True, f"no k8s mapping for '{action}' — noted only")
        except Exception as exc:
            return ActionResult(False, f"kubectl {action} failed: {exc}")

    def rollback(self, action: str, service: str, value: float) -> bool:
        try:
            if action in ("scale", "pool-resize"):
                target = max(1, self._replicas(service) - int(value))
                self._kubectl("scale", f"deployment/{service}", f"--replicas={target}")
                return True
            if action == "rollback":
                self._kubectl("rollout", "undo", f"deployment/{service}")
                return True
        except Exception:
            return False
        return False


class ShellAdapter(Adapter):
    """Generic escape hatch: run a configured command per action.

    Set e.g. CHRONOLENS_CMD_SCALE="./scale.sh {service} {value}". Placeholders
    {service} and {value} are substituted (and shell-quoted).
    """

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg

    def _cmd(self, action: str) -> str | None:
        return os.getenv("CHRONOLENS_CMD_" + action.replace("-", "_").upper())

    def _run(self, tmpl: str, service: str, value: float) -> ActionResult:
        cmd = tmpl.replace("{service}", shlex.quote(service)).replace("{value}", str(value))
        try:
            out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return ActionResult(out.returncode == 0, (out.stdout or out.stderr).strip()[:200])
        except Exception as exc:
            return ActionResult(False, f"shell action failed: {exc}")

    def apply(self, action: str, service: str, value: float) -> ActionResult:
        tmpl = self._cmd(action)
        if not tmpl:
            return ActionResult(False, f"no CHRONOLENS_CMD_{action.upper()} configured")
        return self._run(tmpl, service, value)

    def rollback(self, action: str, service: str, value: float) -> bool:
        tmpl = self._cmd(action + "-undo") or self._cmd("undo")
        if not tmpl:
            return False
        return self._run(tmpl, service, value).ok


def get_adapter(cfg: Config) -> Adapter:
    return {"kubernetes": KubernetesAdapter, "shell": ShellAdapter}.get(
        cfg.adapter, DemoStoreAdapter)(cfg)
