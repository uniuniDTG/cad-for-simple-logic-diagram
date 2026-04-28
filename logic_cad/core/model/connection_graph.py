"""Port compatibility rules and wire endpoint graph."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConnectionGraph:
    """Logical edges from WIRE XDATA (src_uid, dst_uid, ...)."""

    edges: list[tuple[str, str, str]] = field(default_factory=list)  # (src_uid, dst_uid, wire_uid)

    def add_wire(self, src_uid: str, dst_uid: str, wire_uid: str) -> None:
        self.edges.append((src_uid, dst_uid, wire_uid))


def ports_compatible(unit_a: str, unit_b: str) -> bool:
    """Return True for all currently supported port units.

    Current policy is intentionally permissive: LOGIC / VALUE / MULTI / COM are
    all connectable with each other.
    """
    _ = unit_a
    _ = unit_b
    return True


def resolve_wire_unit(a: str, b: str) -> str:
    """Concrete unit for WIRE XDATA when one side is MULTI."""
    ua, ub = a.upper(), b.upper()
    if ua == "COM" or ub == "COM":
        return "COM"
    if ua == "MULTI" and ub == "MULTI":
        return "LOGIC"
    if ua == "MULTI":
        return ub
    if ub == "MULTI":
        return ua
    return ua
