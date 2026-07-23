"""BEHAVIOR DRIFT — "did my agent quietly change?"

Latency and error rate can look perfectly flat while an agent's *behavior*
changes underneath you: after a prompt tweak or a model swap it starts calling a
new tool, taking more steps, or writing much longer answers. No error fires, so
normal monitoring is blind to it.

This builds a **behavior fingerprint** from an agent's traces (which tools, how
often, how many steps, how many tokens, which model) and scores how far a recent
window has drifted from a learned baseline. Drift is a *change* signal, not a
*bad* verdict — a real quality signal decides good-vs-bad, and good drift just
becomes the new baseline (see the notes in the design doc).
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass, field


@dataclass
class Fingerprint:
    n: int
    tool_freq: dict[str, float]      # normalized tool-usage distribution
    model_freq: dict[str, float]     # normalized model mix
    avg_steps: float
    avg_tokens: float


@dataclass
class Drift:
    score: float                     # 0..1 — how far behavior moved
    drifted: bool
    changes: list[str] = field(default_factory=list)
    baseline_n: int = 0
    recent_n: int = 0


def _norm(counter: Counter) -> dict[str, float]:
    total = sum(counter.values())
    return {k: v / total for k, v in counter.items()} if total else {}


def fingerprint(turns: list[dict]) -> Fingerprint:
    """Summarize a set of agent turns into a behavior fingerprint."""
    tools: Counter = Counter()
    models: Counter = Counter()
    steps: list[float] = []
    tokens: list[float] = []
    for t in turns:
        for tool in (t.get("tools") or []):
            tools[tool] += 1
        if t.get("model"):
            models[t["model"]] += 1
        steps.append(float(t.get("steps", len(t.get("tools") or []))))
        tokens.append(float(t.get("output_tokens", 0)))
    n = len(turns)
    return Fingerprint(
        n=n, tool_freq=_norm(tools), model_freq=_norm(models),
        avg_steps=round(sum(steps) / n, 2) if n else 0.0,
        avg_tokens=round(sum(tokens) / n, 1) if n else 0.0,
    )


def _tv(a: dict[str, float], b: dict[str, float]) -> float:
    """Total-variation distance between two distributions (0..1)."""
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def _rel_change(base: float, recent: float) -> float:
    return min(1.0, abs(recent - base) / base) if base else (1.0 if recent else 0.0)


def drift_score(baseline: Fingerprint, recent: Fingerprint,
                *, threshold: float = 0.35) -> Drift:
    """Score how far ``recent`` behavior has drifted from ``baseline``."""
    tool_tv = _tv(baseline.tool_freq, recent.tool_freq)
    model_tv = _tv(baseline.model_freq, recent.model_freq)
    step_ch = _rel_change(baseline.avg_steps, recent.avg_steps)
    tok_ch = _rel_change(baseline.avg_tokens, recent.avg_tokens)
    score = round(min(1.0, 0.4 * tool_tv + 0.2 * model_tv + 0.2 * step_ch + 0.2 * tok_ch), 3)

    changes: list[str] = []
    new_tools = set(recent.tool_freq) - set(baseline.tool_freq)
    dropped = set(baseline.tool_freq) - set(recent.tool_freq)
    if new_tools:
        changes.append("new tool(s): " + ", ".join(sorted(new_tools)))
    if dropped:
        changes.append("stopped using: " + ", ".join(sorted(dropped)))
    if set(recent.model_freq) != set(baseline.model_freq):
        changes.append(f"model mix {sorted(baseline.model_freq)} → {sorted(recent.model_freq)}")
    if _rel_change(baseline.avg_steps, recent.avg_steps) >= 0.25:
        changes.append(f"steps {baseline.avg_steps} → {recent.avg_steps}")
    if _rel_change(baseline.avg_tokens, recent.avg_tokens) >= 0.25:
        pct = (recent.avg_tokens - baseline.avg_tokens) / baseline.avg_tokens * 100 if baseline.avg_tokens else 0
        changes.append(f"answer length {baseline.avg_tokens}→{recent.avg_tokens} tokens ({pct:+.0f}%)")

    return Drift(score=score, drifted=score >= threshold, changes=changes,
                 baseline_n=baseline.n, recent_n=recent.n)


# --- baseline persistence (so a baseline survives across runs) -------------
def _baseline_path(root: str | None = None) -> str:
    root = root or os.path.join(os.path.dirname(__file__), "..", "..", "ledger")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "agent_baseline.json")


def save_baseline(fp: Fingerprint, root: str | None = None) -> None:
    with open(_baseline_path(root), "w", encoding="utf-8") as fh:
        json.dump(asdict(fp), fh, indent=2)


def load_baseline(root: str | None = None) -> Fingerprint | None:
    path = _baseline_path(root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return Fingerprint(**json.load(fh))
    except Exception:
        return None
