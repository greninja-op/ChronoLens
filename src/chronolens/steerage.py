"""Telemetry-Driven Agent Tool Circuit Breaking & Dynamic Steerage.

Allows ChronoLens to intercept AI agent loops and degraded tools based on
real-time OpenTelemetry span metrics from SigNoz.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ToolHealth:
    name: str
    failure_count: int = 0
    total_latency_ms: float = 0.0
    call_count: int = 0
    is_open: bool = False  # True when circuit is open (tool broken)
    opened_at: float = 0.0


@dataclass
class ToolCircuitBreaker:
    failure_threshold: int = 3
    latency_threshold_ms: float = 2500.0
    cooldown_s: float = 60.0
    tools: Dict[str, ToolHealth] = field(default_factory=dict)

    def record_call(self, tool_name: str, latency_ms: float, success: bool = True) -> ToolHealth:
        if tool_name not in self.tools:
            self.tools[tool_name] = ToolHealth(name=tool_name)
        
        health = self.tools[tool_name]
        health.call_count += 1
        health.total_latency_ms += latency_ms

        if not success or latency_ms > self.latency_threshold_ms:
            health.failure_count += 1
        else:
            health.failure_count = max(0, health.failure_count - 1)

        if health.failure_count >= self.failure_threshold and not health.is_open:
            health.is_open = True
            health.opened_at = time.time()

        return health

    def is_tool_available(self, tool_name: str) -> bool:
        if tool_name not in self.tools:
            return True
        health = self.tools[tool_name]
        if health.is_open:
            if time.time() - health.opened_at > self.cooldown_s:
                # Half-open state: allow trial call
                health.is_open = False
                health.failure_count = 0
                return True
            return False
        return True

    def get_status(self) -> Dict[str, dict]:
        return {
            name: {
                "is_open": h.is_open,
                "failures": h.failure_count,
                "avg_latency_ms": (h.total_latency_ms / h.call_count) if h.call_count > 0 else 0.0,
                "calls": h.call_count,
            }
            for name, h in self.tools.items()
        }


def build_steerage_prompt(tool_name: str, reason: str = "degraded or looping") -> str:
    """Generate a dynamic system steerage instruction for the AI agent."""
    return (
        f"[SYSTEM STEERAGE NOTICE]: The tool '{tool_name}' is currently {reason}. "
        f"Do NOT execute '{tool_name}' again during this turn. "
        f"Synthesize your final response now using the information already retrieved."
    )


def steer_agent_context(messages: List[dict], tool_name: str, reason: str = "degraded or looping") -> List[dict]:
    """Inject a steerage instruction into an agent's context window without losing user history."""
    steerage_msg = {
        "role": "system",
        "content": build_steerage_prompt(tool_name, reason=reason),
    }
    updated = list(messages)
    updated.append(steerage_msg)
    return updated
