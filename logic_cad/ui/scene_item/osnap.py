"""Minimal OSNAP candidate selection for editor interactions.

Supported candidate kinds are intentionally limited:

- Selected ``USER_LINE`` endpoints
- ``LD_PORT`` points (wire ports)

The caller controls which kinds are enabled for each interaction mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem

from logic_cad.ui.items.user_geometry_items import UserLineItem
from logic_cad.ui.scene_item.hits import DEFAULT_SCENE_HIT_TOL_MM
from logic_cad.ui.snap_utils import dxf_from_scene_pos, scene_pos_from_dxf


class PortSnapTarget(Protocol):
    """Port-bearing item required by wire-port OSNAP."""

    def port_keys(self) -> tuple[str, ...]:
        """Return available port keys on the item."""

    def port_scene_pos(self, port_key: str) -> QPointF | None:
        """Return scene point for the given port key."""


@dataclass(frozen=True)
class OsnapCandidate:
    """Resolved OSNAP candidate in scene and DXF coordinates."""

    kind: str
    scene_pos: QPointF
    dxf_pos: tuple[float, float]
    dist_sq_mm: float
    symbol_uid: str | None = None
    port_key: str | None = None


def _dist_sq_dxf(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    return dx * dx + dy * dy


def _nearest_user_line_endpoint_candidate(
    scene_pos: QPointF,
    selected_items: list[QGraphicsItem],
    tol_mm: float,
) -> OsnapCandidate | None:
    cursor_dxf = dxf_from_scene_pos(scene_pos)
    tol_sq = float(tol_mm) * float(tol_mm)
    best: OsnapCandidate | None = None
    for item in selected_items:
        if not isinstance(item, UserLineItem):
            continue
        p0_dxf, p1_dxf = item.line_endpoints_dxf()
        for dxf_pt in (p0_dxf, p1_dxf):
            dist_sq = _dist_sq_dxf(cursor_dxf, dxf_pt)
            if dist_sq > tol_sq:
                continue
            if best is None or dist_sq < best.dist_sq_mm:
                best = OsnapCandidate(
                    kind="user_line_endpoint",
                    scene_pos=scene_pos_from_dxf(float(dxf_pt[0]), float(dxf_pt[1])),
                    dxf_pos=(float(dxf_pt[0]), float(dxf_pt[1])),
                    dist_sq_mm=dist_sq,
                )
    return best


def _nearest_wire_port_candidate(
    scene_pos: QPointF,
    symbol_items: dict[str, PortSnapTarget],
    tol_mm: float,
) -> OsnapCandidate | None:
    cursor_dxf = dxf_from_scene_pos(scene_pos)
    tol_sq = float(tol_mm) * float(tol_mm)
    best: OsnapCandidate | None = None
    for uid, sym in symbol_items.items():
        for port_key in sym.port_keys():
            port_scene = sym.port_scene_pos(port_key)
            if port_scene is None:
                continue
            port_dxf = dxf_from_scene_pos(port_scene)
            dist_sq = _dist_sq_dxf(cursor_dxf, port_dxf)
            if dist_sq > tol_sq:
                continue
            if best is None or dist_sq < best.dist_sq_mm:
                best = OsnapCandidate(
                    kind="wire_port",
                    scene_pos=scene_pos_from_dxf(float(port_dxf[0]), float(port_dxf[1])),
                    dxf_pos=(float(port_dxf[0]), float(port_dxf[1])),
                    dist_sq_mm=dist_sq,
                    symbol_uid=str(uid),
                    port_key=str(port_key),
                )
    return best


def pick_osnap_candidate(
    scene_pos: QPointF,
    *,
    selected_items: list[QGraphicsItem],
    symbol_items: dict[str, PortSnapTarget],
    include_user_line_endpoints: bool,
    include_wire_ports: bool,
    tol_mm: float = DEFAULT_SCENE_HIT_TOL_MM,
) -> OsnapCandidate | None:
    """Return a minimal OSNAP candidate by fixed priority.

    Priority:
        1. Selected ``USER_LINE`` endpoint
        2. ``LD_PORT`` (wire port)
        3. None
    """
    if include_user_line_endpoints:
        user_line = _nearest_user_line_endpoint_candidate(scene_pos, selected_items, tol_mm)
        if user_line is not None:
            return user_line
    if include_wire_ports:
        wire_port = _nearest_wire_port_candidate(scene_pos, symbol_items, tol_mm)
        if wire_port is not None:
            return wire_port
    return None
