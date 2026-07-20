"""Pluggable natural-language explanations.

There's always a rule-based explanation built from the evidence, so ChronoLens
runs with no API key. If ``LLM_PROVIDER`` is set (openai | bedrock | gemini),
the model gets a chance to enrich that explanation — but any failure falls back
to the rule-based text. The loop never depends on an LLM being reachable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Config


@dataclass
class Explanation:
    text: str
    source: str  # "rule-based" | provider name


def rule_based(evidence: dict) -> str:
    """A concrete, non-generic explanation assembled from the evidence."""
    svc = evidence.get("service", "the service")
    signal = evidence.get("signal", "load")
    action = evidence.get("action", "a reversible action")
    slope = evidence.get("slope_ms_per_s")
    eta = evidence.get("eta_s")
    root = evidence.get("blast_root")

    reason = {
        "load": "broad latency was rising as demand outran capacity",
        "dependency": "one downstream hop was dragging the whole request",
        "pool": "the connection pool was saturating",
        "memory": "memory was creeping toward the ceiling",
        "errors": "the error rate jumped right after a change",
    }.get(signal, "latency was trending toward the SLO")

    bits = [f"On {svc}, {reason}"]
    if slope:
        bits.append(f"(p99 climbing ~{slope:.0f}ms/s")
        bits[-1] += f", ETA to breach ~{eta:.0f}s)." if eta else ")."
    else:
        bits[-1] += "."
    if root:
        bits.append(f"The blast path traces back to '{root}'.")
    bits.append(f"ChronoLens applied '{action}', which is reversible, so a wrong guess "
                f"costs a brief over-provision — not an outage.")
    return " ".join(bits)


def build_prompt(evidence: dict) -> str:
    return (
        "You are an SRE. In 2-3 concrete sentences, explain this predicted incident "
        "and why the chosen reversible remediation is appropriate. Avoid generic advice.\n"
        + str(evidence)
    )


def explain(evidence: dict, cfg: Config | None = None) -> Explanation:
    """Return an explanation, enriched by an LLM when one is configured."""
    cfg = cfg or Config.load()
    base = rule_based(evidence)
    provider = cfg.llm_provider
    if provider in ("", "none"):
        return Explanation(base, "rule-based")
    try:
        prompt = build_prompt(evidence)
        if provider == "openai":
            text = _openai(prompt, cfg)
        elif provider == "gemini":
            text = _gemini(prompt, cfg)
        elif provider == "bedrock":
            text = _bedrock(prompt, cfg)
        else:
            return Explanation(base, "rule-based")
        text = (text or "").strip()
        return Explanation(text, provider) if text else Explanation(base, "rule-based")
    except Exception:  # fail open — rule-based is always the safety net
        return Explanation(base, "rule-based")


def _openai(prompt: str, cfg: Config) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key)
    resp = client.chat.completions.create(
        model=cfg.openai_model,
        messages=[
            {"role": "system", "content": "You are a concise, concrete SRE assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


def _gemini(prompt: str, cfg: Config) -> str:
    import google.generativeai as genai

    genai.configure(api_key=cfg.openai_api_key or "")
    model = genai.GenerativeModel("gemini-1.5-flash")
    return model.generate_content(prompt).text


def _bedrock(prompt: str, cfg: Config) -> str:
    import json

    import boto3

    client = boto3.client("bedrock-runtime", region_name=cfg.aws_region)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = client.invoke_model(modelId=cfg.bedrock_model, body=json.dumps(body))
    payload = json.loads(resp["body"].read())
    return payload["content"][0]["text"]
