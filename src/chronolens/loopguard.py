"""LOOP GUARD — catch an agent spiralling before the cost does.

An agent can get stuck reasoning in a circle: calling the same tool over and
over, burning tokens and money, with no crash and normal latency. Timeouts are
the crude answer (fire on the clock); this fires on **no progress** — the same
tool repeating without converging — and on a **cost budget per turn**, so it
catches the spiral fast *and* leaves genuinely long, productive turns alone.

The decision is pure (testable without a live agent). The action is a hard stop
(you can't un-spend tokens), so this is a circuit breaker, not a rollback.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass
class LoopVerdict:
    looping: bool
    steps: int
    cost_usd: float
    dominant_tool: str
    dominant_frac: float          # how much of the turn was one repeated tool
    distinct_tools: int
    reason: str
    break_at_step: int | None     # where the breaker would have cut it off
    projected_cost_usd: float     # cost if left to finish
    saved_usd: float              # what the breaker saves vs letting it run


def evaluate(steps: int, tools: list[str], cost_usd: float, *,
             max_steps: int = 6, cost_budget: float = 0.05,
             repeat_threshold: int = 4) -> LoopVerdict:
    """Decide whether a single agent turn is a runaway loop.

    "Stuck" = the same tool repeated with no new variety (no progress), or the
    step/cost ceiling breached. "Busy but productive" = many *different* tools
    (variety) stays allowed even if it's a long turn.
    """
    tools = list(tools or [])
    n = len(tools)
    counts = Counter(tools)
    dom, dom_n = counts.most_common(1)[0] if tools else ("", 0)
    frac = (dom_n / n) if n else 0.0
    distinct = len(counts)
    per_step = (cost_usd / steps) if steps else 0.0

    # "productive" = lots of *variety* and no single tool dominating.
    # A long turn made of many different tools is real work, not a spiral.
    productive = distinct >= max(4, max_steps) and frac < 0.5

    reasons: list[str] = []
    looping = False
    break_at = None

    # 1) no-progress: one tool dominates and repeats past the threshold
    if dom_n >= repeat_threshold and frac >= 0.6:
        looping = True
        reasons.append(f"tool '{dom}' repeated {dom_n}x ({frac:.0%} of the turn) — no progress")
        break_at = repeat_threshold
    # 2) step ceiling — a hint, but only when the turn ISN'T high-variety
    if steps > max_steps and not productive:
        looping = True
        reasons.append(f"{steps} steps over the {max_steps}-step ceiling, low variety")
        break_at = min(break_at or max_steps, max_steps)
    # 3) cost budget — a hard cap; money doesn't care about variety
    if cost_usd > cost_budget:
        looping = True
        reasons.append(f"turn cost ${cost_usd:.4f} over the ${cost_budget:.4f} budget")
        budget_step = int(cost_budget / per_step) if per_step else max_steps
        break_at = min(break_at if break_at is not None else budget_step, budget_step)

    if not looping and productive:
        reasons = [f"long but productive: {distinct} distinct tools, no single tool dominates"]

    projected = round(cost_usd, 5)
    cost_at_break = round(per_step * break_at, 5) if break_at is not None else projected
    saved = round(max(0.0, projected - cost_at_break), 5)
    return LoopVerdict(
        looping=looping, steps=steps, cost_usd=round(cost_usd, 5),
        dominant_tool=dom, dominant_frac=round(frac, 2), distinct_tools=distinct,
        reason="; ".join(reasons) or "within limits", break_at_step=break_at,
        projected_cost_usd=projected, saved_usd=saved,
    )
