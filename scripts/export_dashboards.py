"""Export ChronoLens's SigNoz dashboards as importable JSON.

Judges shouldn't have to run the project to see the dashboards. This writes the
*same* payloads the loop files over the API into ``dashboards/*.json``, ready to
paste into SigNoz → Dashboards → **+ New dashboard** → **Import JSON**.

    python scripts/export_dashboards.py

Keeping this generated from the builders (rather than hand-maintained) means the
committed JSON can't drift from what the code actually files.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronolens.signoz import build_agent_dashboard, build_guard_dashboard  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "dashboards"

AGENT = os.getenv("AGENT_SERVICE_NAME", "chronolens-agent")
SERVICE = os.getenv("CHRONOLENS_SERVICE", "chronolens-store")
SLO_MS = float(os.getenv("CHRONOLENS_P99_SLO_MS", "500"))
MAX_STEPS = int(os.getenv("CHRONOLENS_AGENT_MAX_STEPS", "6"))
BUDGET = float(os.getenv("CHRONOLENS_AGENT_COST_BUDGET", "0.05"))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "chronolens-agent-watch.json": build_agent_dashboard(
            AGENT, max_steps=MAX_STEPS, cost_budget=BUDGET),
        "chronolens-guard.json": build_guard_dashboard(SERVICE, SLO_MS),
    }
    for name, payload in files.items():
        path = OUT / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(OUT.parent)}  "
              f"({len(payload['widgets'])} panels, {len(payload['layout'])} layout entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
