"""Environment configuration for ChronoLens.

One dataclass holds every knob the loop reads, so behavior is reproducible from
a single ``.env`` file. Everything has a safe default — ChronoLens runs with no
API keys, no LLM, and no notifier configured; those only switch on when you set
the matching environment variable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # load .env if python-dotenv is available
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional
    pass


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    signoz_url: str
    signoz_api_key: str
    signoz_mcp_url: str
    demo_store_url: str
    p99_slo_ms: float

    # --- pluggable LLM (NL explanations; all optional) ---
    llm_provider: str          # none | openai | bedrock | gemini
    openai_api_key: str
    openai_model: str
    bedrock_model: str
    aws_region: str

    # --- cost model (turn capacity units into dollars) ---
    cost_per_unit_hr: float    # $ per capacity unit per hour

    # --- governance / trust ladder ---
    autonomy: str              # suggest | auto | earn
    trust_min_saves: int       # proven saves before "earn" mode goes autonomous

    # --- anti-flap guardrails ---
    min_dwell_s: float         # min seconds between actions on the same service
    max_capacity: float        # ceiling ChronoLens will never scale past

    # --- confidence guard ---
    min_slope_ms_per_s: float  # ignore trends flatter than this (noise floor)
    min_samples: int           # need at least this many polls to act

    # --- notifications (Slack / generic webhook) ---
    notify_webhook_url: str

    @classmethod
    def load(cls) -> "Config":
        return cls(
            signoz_url=os.getenv("SIGNOZ_URL", "http://localhost:8080").rstrip("/"),
            signoz_api_key=os.getenv("SIGNOZ_API_KEY", ""),
            signoz_mcp_url=os.getenv("SIGNOZ_MCP_URL", "http://localhost:8000/mcp").rstrip("/"),
            demo_store_url=os.getenv("DEMO_STORE_URL", "http://localhost:8090").rstrip("/"),
            p99_slo_ms=_f("P99_SLO_MS", 500),
            llm_provider=os.getenv("LLM_PROVIDER", "none").lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            bedrock_model=os.getenv("BEDROCK_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            cost_per_unit_hr=_f("COST_PER_UNIT_HR", 0.65),
            autonomy=os.getenv("CHRONOLENS_AUTONOMY", "auto").lower(),
            trust_min_saves=int(_f("CHRONOLENS_TRUST_MIN_SAVES", 3)),
            min_dwell_s=_f("CHRONOLENS_MIN_DWELL_S", 20),
            max_capacity=_f("CHRONOLENS_MAX_CAPACITY", 12),
            min_slope_ms_per_s=_f("CHRONOLENS_MIN_SLOPE", 3.0),
            min_samples=int(_f("CHRONOLENS_MIN_SAMPLES", 4)),
            notify_webhook_url=os.getenv("CHRONOLENS_WEBHOOK_URL", ""),
        )

    def require_signoz(self) -> None:
        """Fail fast with a clear message if SigNoz creds are missing."""
        if not self.signoz_url or not self.signoz_api_key:
            raise RuntimeError(
                "SIGNOZ_URL and SIGNOZ_API_KEY must be set (copy .env.example to .env)."
            )


# SLO in nanoseconds (SigNoz stores span durations as duration_nano).
def slo_ns(cfg: Config) -> float:
    return cfg.p99_slo_ms * 1e6
