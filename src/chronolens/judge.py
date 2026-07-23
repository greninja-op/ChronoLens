"""QUALITY JUDGE — grade agent answers in production, trend the score.

Everyone watches whether the servers are healthy; almost nobody watches whether
the *answers* are still good. This attaches a lightweight grader to live agent
responses so answer **quality** becomes a first-class, trended signal — you
catch "the answers got worse" the same way you'd catch "latency got worse".

The rule-based grader runs with no API key (heuristics over the response). If an
LLM provider is configured it can grade more richly, but it always falls back to
the rule-based score — the judge never depends on an LLM being reachable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# phrases that suggest the agent stalled, hedged, or didn't actually answer
HEDGES = ["i'm not sure", "im not sure", "still checking", "let me look",
          "i don't know", "i dont know", "unable to", "i cannot", "not certain",
          "let me check", "hold on", "i'll get back"]


@dataclass
class QualityScore:
    score: float                 # 0..1, higher = better
    verdict: str                 # good | degraded | bad
    reasons: list[str] = field(default_factory=list)
    source: str = "rule-based"


def _verdict(score: float) -> str:
    return "good" if score >= 0.7 else "degraded" if score >= 0.4 else "bad"


def rule_based(answer: str, *, baseline_len: int = 160) -> QualityScore:
    """Heuristic grade over a single response. Cheap, explainable, no key."""
    a = (answer or "").lower().strip()
    length = len(answer or "")
    score = 1.0
    reasons: list[str] = []

    if any(h in a for h in HEDGES):
        score -= 0.45
        reasons.append("hedging / didn't actually resolve the request")
    if length < 15:
        score -= 0.35
        reasons.append("too short — no real answer")
    elif length > baseline_len * 2.5:
        score -= 0.30
        reasons.append(f"unusually long ({length} chars vs ~{baseline_len}) — rambling")

    score = max(0.0, round(score, 2))
    if not reasons:
        reasons.append("concise and on-point")
    return QualityScore(score=score, verdict=_verdict(score), reasons=reasons, source="rule-based")


def score_response(answer: str, cfg=None, *, baseline_len: int = 160) -> QualityScore:
    """Grade a response — LLM-enriched when configured, else rule-based."""
    base = rule_based(answer, baseline_len=baseline_len)
    provider = getattr(cfg, "llm_provider", "none") if cfg else "none"
    if provider in ("", "none", None):
        return base
    try:
        val = _llm_score(answer, cfg)
        if val is not None:
            return QualityScore(score=round(val, 2), verdict=_verdict(val),
                                reasons=["graded by LLM judge"], source=provider)
    except Exception:
        pass
    return base  # fail open to the rule-based grade


def grade_batch(answers: list[str], cfg=None, *, baseline_len: int = 160) -> dict:
    """Grade several answers and summarize the trend."""
    scores = [score_response(a, cfg, baseline_len=baseline_len) for a in answers]
    vals = [s.score for s in scores]
    avg = round(sum(vals) / len(vals), 2) if vals else 0.0
    return {
        "avg_score": avg,
        "verdict": _verdict(avg),
        "n": len(scores),
        "degraded_pct": round(100 * sum(1 for s in scores if s.verdict != "good") / len(scores), 0) if scores else 0,
        "samples": [s.__dict__ for s in scores],
    }


def _llm_score(answer: str, cfg) -> float | None:
    """Ask a configured LLM for a 0..1 quality score. Best-effort."""
    prompt = ("Rate this customer-support answer for helpfulness and completeness "
              "from 0.0 (useless) to 1.0 (excellent). Reply with only the number.\n\n" + answer)
    provider = cfg.llm_provider
    text = None
    if provider == "openai":
        from openai import OpenAI
        c = OpenAI(api_key=cfg.openai_api_key)
        text = c.chat.completions.create(
            model=cfg.openai_model, temperature=0,
            messages=[{"role": "user", "content": prompt}]).choices[0].message.content
    elif provider == "bedrock":
        import json as _j
        import boto3
        c = boto3.client("bedrock-runtime", region_name=cfg.aws_region)
        body = {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 8,
                "messages": [{"role": "user", "content": prompt}]}
        text = _j.loads(c.invoke_model(modelId=cfg.bedrock_model, body=_j.dumps(body))
                        ["body"].read())["content"][0]["text"]
    if text is None:
        return None
    import re
    m = re.search(r"[01](?:\.\d+)?", text)
    return max(0.0, min(1.0, float(m.group()))) if m else None
