"""BLAST-RADIUS FORECAST — who falls next, in what order, and when.

Every reliability tool tells you *this service is unhealthy*. That's the symptom.
In a distributed system the interesting question is the one nobody answers ahead
of time:

    "payment is about to breach — which of my other services go down with it,
     in what order, and how long do I have?"

This module answers that from real SigNoz data:

1. **Topology** — SigNoz's own service dependency map (`service_dependency_edges`)
   gives the real parent → child call graph derived from traces. If that endpoint
   isn't available on the running version, we fall back to a topology inferred
   from per-service span breakdowns, so the feature degrades instead of dying.
2. **Per-service trend** — each service's p99 series comes from the Query Builder,
   analyzed with the same FORESEE machinery (EWMA + Holt + confidence guard).
3. **Propagation** — a caller can't be faster than the dependency it waits on, so
   a degrading child pushes latency up into every ancestor. We walk the graph
   upward from the root, adding the child's *excess* latency (scaled by how much
   of the parent's time is spent in that child) to each ancestor's projection,
   and compute each one's own time-to-breach.
4. **Ranking** — the result is an ordered timeline of predicted victims, with the
   root cause named, so remediation targets the cause instead of the loudest alarm.

Everything is labelled by provenance (`measured` vs `projected`) for the same
reason Chrono-Proof is: an estimate must never read as a measurement.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .config import Config
from .foresee import analyze


@dataclass
class Victim:
    service: str
    depth: int                       # hops away from the root (0 = the root itself)
    current_p99_ms: float            # measured, from SigNoz
    slope_ms_per_s: float            # measured trend
    inherited_ms_per_s: float        # extra slope pushed up from the dependency
    effective_slope_ms_per_s: float  # own + inherited
    seconds_to_breach: float | None  # projected
    breaching_now: bool
    confidence: float
    is_root: bool = False
    via: str = ""                    # the dependency it inherits pressure from


@dataclass
class BlastRadius:
    ok: bool
    slo_ms: float
    root_service: str = ""
    root_span: str = ""
    topology_source: str = "unavailable"   # "signoz-service-map" | "span-breakdown" | "unavailable"
    edges: list[dict[str, Any]] = field(default_factory=list)
    victims: list[Victim] = field(default_factory=list)
    narrative: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["victims"] = [asdict(v) for v in self.victims]
        return d


# --------------------------------------------------------------------------- #
# graph helpers (pure — unit-testable without SigNoz)
# --------------------------------------------------------------------------- #
def build_parent_index(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    """child -> [parents]. Parents wait on children, so pressure flows upward."""
    idx: dict[str, list[str]] = {}
    for e in edges:
        child, parent = e.get("child"), e.get("parent")
        if child and parent and parent != child:
            idx.setdefault(str(child), []).append(str(parent))
    return idx


def ancestors_of(service: str, parent_index: dict[str, list[str]],
                 *, max_depth: int = 6) -> list[tuple[str, int, str]]:
    """Breadth-first walk upward. Returns [(service, depth, via_child), ...]."""
    seen = {service}
    out: list[tuple[str, int, str]] = []
    frontier = [(service, 0)]
    while frontier:
        node, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for parent in parent_index.get(node, []):
            if parent in seen:
                continue
            seen.add(parent)
            out.append((parent, depth + 1, node))
            frontier.append((parent, depth + 1))
    return out


def pick_root(forecasts: dict[str, Any], parent_index: dict[str, list[str]]) -> str:
    """The root is the *most downstream* service that is degrading.

    A leaf (something nothing else depends on downstream of it) that is climbing
    is a cause; a service that is climbing only because its dependency is slow is
    a symptom. Prefer the deepest degrading node, tie-broken by steepest slope.
    """
    if not forecasts:
        return ""
    # depth = how many services sit above it (are its ancestors)
    def upstream_count(svc: str) -> int:
        return len(ancestors_of(svc, parent_index))

    climbing = {s: f for s, f in forecasts.items() if getattr(f, "slope_ms_per_s", 0) > 0}
    pool = climbing or forecasts
    return max(pool, key=lambda s: (upstream_count(s), pool[s].slope_ms_per_s))


def _share(edges: list[dict[str, Any]], parent: str, child: str) -> float:
    """Fraction of the parent's outbound calls that go to this child (0.2..1.0).

    Used to scale how much of the child's excess latency the parent actually
    absorbs. Falls back to 1.0 when SigNoz gave us no call counts.
    """
    total = sum(e.get("callCount", 0.0) for e in edges if e.get("parent") == parent)
    if not total:
        return 1.0
    this = sum(e.get("callCount", 0.0) for e in edges
               if e.get("parent") == parent and e.get("child") == child)
    return max(0.2, min(1.0, this / total)) if this else 0.2


def forecast_blast_radius(series_by_service: dict[str, list[float]],
                          edges: list[dict[str, Any]], *, slo_ms: float,
                          step_s: float = 15.0,
                          topology_source: str = "signoz-service-map",
                          min_samples: int = 4,
                          min_slope_ms_per_s: float = 3.0) -> BlastRadius:
    """Predict the ordered set of services a degradation will take down.

    Pure function: give it p99 series per service + dependency edges and it
    returns the ranked victim timeline. No I/O, so it's fully testable.
    """
    if not series_by_service:
        return BlastRadius(ok=False, slo_ms=slo_ms, topology_source="unavailable",
                           notes=["no per-service p99 series available"])

    forecasts = {}
    for svc, series in series_by_service.items():
        if not series:
            continue
        fc = analyze(series, step_s, slo_ms, min_samples=min_samples,
                     min_slope_ms_per_s=min_slope_ms_per_s, lead_window_s=600.0)
        fc.service = svc
        forecasts[svc] = fc
    if not forecasts:
        return BlastRadius(ok=False, slo_ms=slo_ms, topology_source=topology_source,
                           notes=["every service returned an empty series"])

    parent_index = build_parent_index(edges)
    root = pick_root(forecasts, parent_index)
    root_fc = forecasts[root]

    victims: list[Victim] = [Victim(
        service=root, depth=0, current_p99_ms=root_fc.current_p99_ms,
        slope_ms_per_s=round(root_fc.slope_ms_per_s, 2), inherited_ms_per_s=0.0,
        effective_slope_ms_per_s=round(root_fc.slope_ms_per_s, 2),
        seconds_to_breach=root_fc.seconds_to_breach,
        breaching_now=root_fc.breaching_now, confidence=root_fc.confidence,
        is_root=True,
    )]

    # Pressure flows upward: each ancestor inherits the root's excess rate,
    # scaled by how much of its traffic actually depends on that path.
    for svc, depth, via in ancestors_of(root, parent_index):
        fc = forecasts.get(svc)
        if fc is None:
            continue
        inherited = round(max(0.0, root_fc.slope_ms_per_s) * _share(edges, svc, via)
                          / (1 + 0.35 * (depth - 1)), 2)
        eff = round(max(0.0, fc.slope_ms_per_s) + inherited, 2)
        eta: float | None = None
        if fc.current_p99_ms >= slo_ms:
            eta = 0.0
        elif eff > 0:
            eta = round((slo_ms - fc.current_p99_ms) / eff, 1)
        victims.append(Victim(
            service=svc, depth=depth, current_p99_ms=fc.current_p99_ms,
            slope_ms_per_s=round(fc.slope_ms_per_s, 2), inherited_ms_per_s=inherited,
            effective_slope_ms_per_s=eff, seconds_to_breach=eta,
            breaching_now=fc.current_p99_ms >= slo_ms, confidence=fc.confidence,
            via=via,
        ))

    # Order by when each one actually falls.
    victims.sort(key=lambda v: (v.seconds_to_breach is None,
                                v.seconds_to_breach if v.seconds_to_breach is not None else 1e9))

    br = BlastRadius(ok=True, slo_ms=slo_ms, root_service=root,
                     topology_source=topology_source, edges=edges, victims=victims)
    br.narrative = _narrate(br)
    br.notes.append("Current p99 and per-service trends are measured from SigNoz. "
                    "Time-to-breach and inherited slope are projections.")
    if not edges:
        br.notes.append("No dependency edges available — showing the root only, "
                        "propagation needs SigNoz's service map.")
    return br


def _narrate(br: BlastRadius) -> str:
    if not br.victims:
        return "Nothing degrading right now."
    falling = [v for v in br.victims if v.seconds_to_breach is not None]
    if not falling:
        return (f"{br.root_service} is the deepest degrading service, but nothing is "
                f"projected to cross the {br.slo_ms:.0f}ms SLO in this window.")
    parts = []
    for v in falling[:4]:
        when = "now" if (v.breaching_now or v.seconds_to_breach == 0) else f"~{v.seconds_to_breach:.0f}s"
        tag = " (root)" if v.is_root else f" (via {v.via})" if v.via else ""
        parts.append(f"{v.service}{tag} {when}")
    return (f"Blast radius from {br.root_service}: " + " → ".join(parts) +
            f". Fixing {br.root_service} stops the chain; patching the services above it "
            f"only mutes the alarm.")


# --------------------------------------------------------------------------- #
# live path
# --------------------------------------------------------------------------- #
def blast_radius_from_signoz(sn, cfg: Config, *, window_seconds: int = 300,
                             step_interval: int = 15,
                             max_services: int = 8) -> BlastRadius:
    """Read topology + per-service p99 series from SigNoz and forecast the blast radius."""
    try:
        services = [s.get("serviceName") for s in sn.list_services(window_seconds=window_seconds)]
        services = [s for s in services if s and s != "chronolens"][:max_services]
    except Exception as exc:
        return BlastRadius(ok=False, slo_ms=cfg.p99_slo_ms, topology_source="unavailable",
                           notes=[f"SigNoz service list failed: {exc}"])
    if not services:
        return BlastRadius(ok=False, slo_ms=cfg.p99_slo_ms, topology_source="unavailable",
                           notes=["SigNoz reported no services in this window"])

    edges: list[dict[str, Any]] = []
    topology_source = "unavailable"
    try:
        edges = sn.service_dependency_edges(window_seconds=max(window_seconds, 900))
        if edges:
            topology_source = "signoz-service-map"
    except Exception:
        edges = []
    if not edges:
        edges, topology_source = _edges_from_spans(sn, services)

    series_by_service: dict[str, list[float]] = {}
    for svc in services:
        try:
            series_by_service[svc] = sn.service_p99_series(
                svc, window_seconds=window_seconds, step_interval=step_interval)
        except Exception:
            continue

    br = forecast_blast_radius(series_by_service, edges, slo_ms=cfg.p99_slo_ms,
                               step_s=float(step_interval),
                               topology_source=topology_source,
                               min_samples=cfg.min_samples,
                               min_slope_ms_per_s=cfg.min_slope_ms_per_s)
    # Name the root *span* too (the exact hop to fix), from the trace breakdown.
    if br.ok and br.root_service:
        try:
            br.root_span = sn.dominant_span(br.root_service) or ""
        except Exception:
            br.root_span = ""
    return br


def _edges_from_spans(sn, services: list[str]) -> tuple[list[dict[str, Any]], str]:
    """Fallback topology: infer edges by matching span names to service names.

    If a service's trace spans reference another service's name, treat that as a
    dependency. Crude but real (it comes from traces), and it keeps the feature
    working on SigNoz builds without a service-map endpoint.
    """
    edges: list[dict[str, Any]] = []
    for parent in services:
        try:
            breakdown = sn.span_p99_breakdown(parent)
        except Exception:
            continue
        for span_name in breakdown:
            low = span_name.lower()
            for child in services:
                if child == parent:
                    continue
                key = child.lower().replace("-service", "").replace("-", "")
                if key and key in low.replace("-", "").replace(".", ""):
                    edges.append({"parent": parent, "child": child, "callCount": 1.0})
                    break
    return edges, ("span-breakdown" if edges else "unavailable")
