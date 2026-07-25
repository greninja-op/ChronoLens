"""Unit tests for the BLAST-RADIUS forecast (pure functions, no SigNoz)."""
from __future__ import annotations

from chronolens.blastradius import (
    ancestors_of,
    build_parent_index,
    forecast_blast_radius,
    pick_root,
)

SLO = 500.0

# orders -> checkout -> payment  (payment is the deepest dependency)
EDGES = [
    {"parent": "orders", "child": "checkout", "callCount": 100.0},
    {"parent": "checkout", "child": "payment", "callCount": 100.0},
]

FLAT = [120.0, 121.0, 119.0, 120.0, 121.0, 120.0]
CLIMB = [200.0, 250.0, 300.0, 350.0, 400.0, 450.0]


def test_parent_index_maps_child_to_parents():
    idx = build_parent_index(EDGES)
    assert idx["payment"] == ["checkout"]
    assert idx["checkout"] == ["orders"]


def test_ancestors_walk_upward_with_depth():
    anc = ancestors_of("payment", build_parent_index(EDGES))
    names = {s: d for s, d, _ in anc}
    assert names == {"checkout": 1, "orders": 2}


def test_root_is_the_deepest_degrading_service():
    """checkout climbing too, but payment is deeper — payment is the cause."""
    class _F:
        def __init__(self, slope):
            self.slope_ms_per_s = slope
    forecasts = {"orders": _F(2.0), "checkout": _F(5.0), "payment": _F(4.0)}
    assert pick_root(forecasts, build_parent_index(EDGES)) == "payment"


def test_climbing_dependency_puts_ancestors_in_the_blast_radius():
    series = {"payment": CLIMB, "checkout": FLAT, "orders": FLAT}
    br = forecast_blast_radius(series, EDGES, slo_ms=SLO, step_s=15.0)
    assert br.ok
    assert br.root_service == "payment"
    names = [v.service for v in br.victims]
    assert set(names) == {"payment", "checkout", "orders"}
    # flat services must inherit pressure from the climbing dependency
    inherited = {v.service: v.inherited_ms_per_s for v in br.victims}
    assert inherited["checkout"] > 0
    assert inherited["orders"] > 0
    assert inherited["payment"] == 0.0   # the root inherits nothing


def test_victims_are_ordered_by_when_they_fall():
    series = {"payment": CLIMB, "checkout": FLAT, "orders": FLAT}
    br = forecast_blast_radius(series, EDGES, slo_ms=SLO, step_s=15.0)
    etas = [v.seconds_to_breach for v in br.victims if v.seconds_to_breach is not None]
    assert etas == sorted(etas)


def test_deeper_ancestors_inherit_less_pressure():
    series = {"payment": CLIMB, "checkout": FLAT, "orders": FLAT}
    br = forecast_blast_radius(series, EDGES, slo_ms=SLO, step_s=15.0)
    by = {v.service: v for v in br.victims}
    assert by["checkout"].inherited_ms_per_s >= by["orders"].inherited_ms_per_s


def test_no_edges_still_reports_the_root_and_says_why():
    br = forecast_blast_radius({"payment": CLIMB}, [], slo_ms=SLO, step_s=15.0,
                               topology_source="unavailable")
    assert br.ok
    assert br.root_service == "payment"
    assert len(br.victims) == 1
    assert any("service map" in n for n in br.notes)


def test_empty_input_fails_soft():
    br = forecast_blast_radius({}, EDGES, slo_ms=SLO)
    assert br.ok is False
    assert br.notes


def test_narrative_names_root_and_provenance_note_present():
    series = {"payment": CLIMB, "checkout": FLAT, "orders": FLAT}
    br = forecast_blast_radius(series, EDGES, slo_ms=SLO, step_s=15.0)
    assert "payment" in br.narrative
    assert any("projection" in n.lower() for n in br.notes)


# --------------------------------------------------------------------------- #
# Root selection must stay inside the dependency graph.                        #
# --------------------------------------------------------------------------- #
class _F:
    def __init__(self, slope): self.slope_ms_per_s = slope


def test_standalone_service_cannot_be_the_root_when_a_graph_exists():
    """A sidecar/agent with no dependencies has no blast path — it isn't a cause."""
    forecasts = {"payment": _F(4.0), "checkout": _F(1.0), "orders": _F(0.5),
                 "some-agent": _F(99.0)}   # steepest, but not in the graph
    root = pick_root(forecasts, build_parent_index(EDGES), EDGES)
    assert root == "payment"


def test_without_a_graph_the_steepest_service_is_still_chosen():
    forecasts = {"lonely": _F(9.0), "quiet": _F(0.1)}
    assert pick_root(forecasts, {}, []) == "lonely"


def test_unconnected_services_are_excluded_from_the_blast_chain():
    series = {"payment": CLIMB, "checkout": FLAT, "orders": FLAT, "some-agent": CLIMB}
    br = forecast_blast_radius(series, EDGES, slo_ms=SLO, step_s=15.0)
    assert br.root_service == "payment"
    assert "some-agent" not in [v.service for v in br.victims]
