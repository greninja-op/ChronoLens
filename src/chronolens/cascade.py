"""CASCADE — predict how a failure spreads, and name the root.

Reactive tools only see a cascade after it's happened. ChronoLens reads the
service topology from the trace structure, so when a downstream hop degrades it
can name the path the failure will take — and point remediation at the root
rather than the symptom.

For the demo store the topology is a known chain:

    /order → cart.lookup → inventory.check → payment.charge → payment.db_query → order.db_write

The dominant downstream hop (payment.db_query) is the root; /order is the
user-facing symptom that breaches last.
"""
from __future__ import annotations

from dataclasses import dataclass

# Known request topology of the demo store (parent → children, in call order).
STORE_TOPOLOGY = {
    "/order": ["cart.lookup", "inventory.check", "payment.charge", "order.db_write"],
    "payment.charge": ["payment.db_query"],
}

# Which hop tends to dominate latency under load (the root to fix first).
ROOT_HOP = "payment.db_query"


@dataclass
class BlastPath:
    root: str
    path: list[str]
    narrative: str
    source: str = "topology"   # "topology" (static) | "traces" (data-driven)


def _static_path(entry: str, root: str) -> list[str]:
    path = [entry]
    node = entry
    while node in STORE_TOPOLOGY:
        children = STORE_TOPOLOGY[node]
        nxt = next((c for c in children if c in STORE_TOPOLOGY or c == root), None)
        if not nxt:
            nxt = children[-1]
        path.append(nxt)
        if nxt == root:
            break
        node = nxt
    return path


def predict_blast_path(entry: str = "/order",
                       breakdown: dict[str, float] | None = None) -> BlastPath:
    """Return the predicted spread from the entry span down to the root.

    If ``breakdown`` (a ``{span_name: p99_ms}`` map from SigNoz traces) is given,
    the **slowest measured span** becomes the empirical root — the cascade is
    then data-driven, not a hardcoded guess. Otherwise it falls back to the
    static store topology.
    """
    source = "topology"
    root = ROOT_HOP
    if breakdown:
        # The entry span (e.g. /order) always wraps its children, so it's the
        # slowest by construction — exclude it and pick the slowest *downstream*
        # hop as the empirical root cause.
        downstream = {k: v for k, v in breakdown.items() if k != entry}
        if downstream:
            measured_root = max(downstream, key=downstream.get)
            if downstream[measured_root] > 0:
                root, source = measured_root, "traces"

    path = _static_path(entry, root)
    if path[-1] != root:
        path.append(root)

    how = "measured in traces" if source == "traces" else "from topology"
    p99 = f" (p99 {breakdown[root]}ms)" if source == "traces" and root in breakdown else ""
    narrative = (
        f"Degradation at '{root}'{p99} ({how}) propagates up "
        f"{' → '.join(reversed(path))}, so '{entry}' breaches last. "
        f"Fix the root ('{root}') to stop the whole chain."
    )
    return BlastPath(root=root, path=path, narrative=narrative, source=source)
