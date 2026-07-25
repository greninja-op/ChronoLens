"""Contract tests: every endpoint the dashboard calls must exist with that HTTP method.

This exists because the UI called `/api/agent/loopcheck` with POST while the route was
a GET, which returned 405 at runtime and silently showed "agent offline" in the panel.
Static checks catch that class of bug without needing a browser.
"""
from __future__ import annotations

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "static", "index.html")
APP = os.path.join(ROOT, "app.py")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _declared_routes() -> dict[tuple[str, str], bool]:
    """{(METHOD, path): True} declared in app.py."""
    app = _read(APP)
    out = {}
    for m, p in re.findall(r'@app\.(get|post)\(\s*"([^"]+)"', app):
        out[(m.upper(), p)] = True
    return out


def _ui_calls() -> set[tuple[str, str]]:
    """{(METHOD, path)} that the dashboard fetches."""
    html = _read(INDEX)
    calls: set[tuple[str, str]] = set()
    for m in re.finditer(r"fetch\(", html):
        # take the whole call expression: from 'fetch(' to its balanced ')'
        i, depth = m.end() - 1, 0
        while i < len(html):
            if html[i] == "(":
                depth += 1
            elif html[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        expr = html[m.end():i]
        url = re.search(r"""[`'"]([^`'"]*/api/[^`'"]*)""", expr)
        if not url:
            continue
        path = re.sub(r"\$\{[^}]*\}", "", url.group(1)).split("?")[0]
        if not path.startswith("/api/"):
            continue
        # 'POST' anywhere in the same call expression means an explicit method
        calls.add(("POST" if "POST" in expr.upper() else "GET", path))
    return calls


def test_dashboard_only_calls_endpoints_that_exist_with_the_right_method():
    declared = _declared_routes()
    problems = []
    for method, path in sorted(_ui_calls()):
        if (method, path) in declared:
            continue
        other = "GET" if method == "POST" else "POST"
        if (other, path) in declared:
            problems.append(f"{path} is declared {other} but the UI calls it {method}")
        else:
            problems.append(f"{method} {path} is called by the UI but not declared in app.py")
    assert not problems, "dashboard/API contract mismatch:\n  - " + "\n  - ".join(problems)


def test_dashboard_has_no_references_to_removed_features():
    html = _read(INDEX)
    dead = re.findall(
        r"/api/(counterfactual|stress|cfo|sarvam|agent/throttle|agent/circuit-break"
        r"|agent/steer|stitch)", html)
    assert not dead, f"dashboard still references removed endpoints: {sorted(set(dead))}"


@pytest.mark.parametrize("needle,why", [
    ("chronolens-logo.png", "the real logo asset must be used in the header"),
    ("--black:#000000", "canvas must be pure black"),
    ("logarithmic", "chart must use a log y-axis so ms and seconds both read"),
    ("scrollbar-gutter", "scrollbars must sit in their own gutter, not over content"),
    ("traffic-ramp", "the inject button must send a fault mode the store understands"),
])
def test_dashboard_design_invariants(needle, why):
    assert needle in _read(INDEX), why
