"""Tests for the SigNoz dashboards ChronoLens auto-files.

Regression origin: both dashboards were created with correct widgets but **no
`layout` and no widget `id`s**. SigNoz stored them without complaint and the UI then
rendered "Welcome to your new dashboard" — an empty dashboard, no error anywhere.
These tests make that specific failure impossible to ship again.
"""
from __future__ import annotations

from chronolens.signoz import build_agent_dashboard, build_guard_dashboard

AGENT = "chronolens-agent"
SERVICE = "chronolens-store"


def _dashboards():
    return [
        ("agent", build_agent_dashboard(AGENT, max_steps=6, cost_budget=0.05)),
        ("guard", build_guard_dashboard(SERVICE, 500.0)),
    ]


def test_every_widget_has_an_id():
    for name, dash in _dashboards():
        for w in dash["widgets"]:
            assert w.get("id"), f"{name}: widget {w.get('title')!r} has no id"


def test_layout_exists_and_covers_every_widget():
    """Without this the dashboard renders empty even though the panels are stored."""
    for name, dash in _dashboards():
        layout = dash.get("layout")
        assert layout, f"{name}: no layout — the dashboard would render empty"
        widget_ids = {w["id"] for w in dash["widgets"]}
        layout_ids = {item["i"] for item in layout}
        assert layout_ids == widget_ids, f"{name}: layout/widget ids disagree"


def test_layout_items_have_grid_geometry():
    for name, dash in _dashboards():
        for item in dash["layout"]:
            for key in ("x", "y", "w", "h"):
                assert key in item, f"{name}: layout item missing {key}"
            assert item["w"] > 0 and item["h"] > 0
            assert 0 <= item["x"] <= 12
            assert item["x"] + item["w"] <= 12, f"{name}: panel overflows the 12-col grid"


def test_widget_ids_are_unique():
    for name, dash in _dashboards():
        ids = [w["id"] for w in dash["widgets"]]
        assert len(ids) == len(set(ids)), f"{name}: duplicate widget ids"


def test_agent_dashboard_covers_the_genai_signals():
    dash = build_agent_dashboard(AGENT)
    blob = str(dash)
    for needle in ("llm.cost_usd", "llm.step_count", "gen_ai.usage.output_tokens",
                   "tool.name", "duration_nano"):
        assert needle in blob, f"agent dashboard missing {needle}"
    # every panel must be scoped to the agent, not the whole workspace
    for w in dash["widgets"]:
        assert AGENT in str(w), f"panel {w['title']!r} isn't filtered to the agent"


def test_guard_dashboard_reads_back_chronolens_own_metric():
    """The full-circle panel: ChronoLens's own metric, read back out of SigNoz."""
    dash = build_guard_dashboard(SERVICE, 500.0)
    assert "chronolens.prevented_total" in str(dash)


def test_latency_panels_use_nanosecond_units():
    """SigNoz stores span duration as duration_nano; a ms unit misplaces the SLO marker."""
    dash = build_guard_dashboard(SERVICE, 500.0)
    latency = dash["widgets"][0]
    assert latency["yAxisUnit"] == "ns"
    assert latency["thresholds"][0]["thresholdValue"] == 500.0 * 1e6
    assert latency["thresholds"][0]["thresholdUnit"] == "ns"


# --------------------------------------------------------------------------- #
# Panels must carry the fields SigNoz's *UI* maps over. The API accepts a panel
# without them and returns 200; the dashboard then renders blank, which is the
# single most confusing failure mode in this integration.
# --------------------------------------------------------------------------- #
_UI_REQUIRED_PANEL_FIELDS = (
    "id", "panelTypes", "title", "query", "thresholds",
    "selectedLogFields", "selectedTracesFields", "contextLinks", "timePreferance",
)


def _all_dashboards():
    return [build_guard_dashboard(SERVICE, 500.0), build_agent_dashboard(AGENT)]


def test_every_panel_carries_the_fields_the_ui_maps_over():
    for dash in _all_dashboards():
        for w in dash["widgets"]:
            for field in _UI_REQUIRED_PANEL_FIELDS:
                assert field in w, f"{dash['title']} / {w.get('title')} missing {field}"
            assert w["contextLinks"] == {"linksData": []} or "linksData" in w["contextLinks"]
            q = w["query"]
            assert q["promql"] == [] or isinstance(q["promql"], list)
            assert isinstance(q["clickhouse_sql"], list)
            # queryFormulas missing means `undefined` in the frontend, not empty.
            assert isinstance(q["builder"]["queryFormulas"], list)


def test_dashboards_declare_variables_and_version():
    for dash in _all_dashboards():
        assert dash["variables"] == {}
        assert dash["version"] == "v5"


def test_thresholds_use_the_long_field_names_the_ui_reads():
    for dash in _all_dashboards():
        for w in dash["widgets"]:
            for t in w["thresholds"]:
                assert "thresholdValue" in t and "thresholdUnit" in t
                assert t["thresholdOperator"] in (">", "<", ">=", "<=", "=")
                assert t["thresholdFormat"] in ("Text", "Background")
                assert t["thresholdColor"].startswith("#")
                assert "value" not in t, "short threshold form draws no marker"


def test_panel_ids_are_deterministic():
    """Re-exporting must not churn dashboards/*.json."""
    a = build_agent_dashboard(AGENT)
    b = build_agent_dashboard(AGENT)
    assert [w["id"] for w in a["widgets"]] == [w["id"] for w in b["widgets"]]
    assert [l["i"] for l in a["layout"]] == [w["id"] for w in a["widgets"]]
