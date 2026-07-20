"""Pytest bootstrap for ChronoLens.

Puts the ``src`` layout on the import path and disables the self-observability
OTLP exporter so tests never try to reach a live collector.
"""
from __future__ import annotations

import os
import sys

# Disable ChronoLens self-OTEL export before any package import initializes it.
os.environ.setdefault("CHRONOLENS_SELF_OTEL", "off")

_HERE = os.path.dirname(__file__)
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
