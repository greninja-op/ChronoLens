"""Environment configuration for ChronoLens."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # load .env if python-dotenv is available
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional
    pass


@dataclass
class Config:
    signoz_url: str
    signoz_api_key: str
    signoz_mcp_url: str
    demo_store_url: str
    llm_provider: str
    p99_slo_ms: float

    @classmethod
    def load(cls) -> "Config":
        return cls(
            signoz_url=os.getenv("SIGNOZ_URL", "http://localhost:8080").rstrip("/"),
            signoz_api_key=os.getenv("SIGNOZ_API_KEY", ""),
            signoz_mcp_url=os.getenv("SIGNOZ_MCP_URL", "http://localhost:8000/mcp").rstrip("/"),
            demo_store_url=os.getenv("DEMO_STORE_URL", "http://localhost:8090").rstrip("/"),
            llm_provider=os.getenv("LLM_PROVIDER", "none").lower(),
            p99_slo_ms=float(os.getenv("P99_SLO_MS", "500")),
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
