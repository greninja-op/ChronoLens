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


def predict_blast_path(entry: str = "/order") -> BlastPath:
    """Return the predicted spread from the entry span down to the root."""
    path = [entry]
    node = entry
    # walk the chain toward the root hop
    while node in STORE_TOPOLOGY:
        children = STORE_TOPOLOGY[node]
        nxt = next((c for c in children if c in STORE_TOPOLOGY or c == ROOT_HOP), None)
        if not nxt:
            # fall through the last child that leads deepest
            nxt = children[-1]
        path.append(nxt)
        if nxt == ROOT_HOP:
            break
        node = nxt

    narrative = (
        f"Degradation at '{ROOT_HOP}' propagates up "
        f"{' → '.join(reversed(path))}, so '{entry}' breaches last. "
        f"Fix the root ('{ROOT_HOP}' capacity) to stop the whole chain."
    )
    return BlastPath(root=ROOT_HOP, path=path, narrative=narrative)
