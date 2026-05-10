"""Thin façade: DXF-derived obstacles plus wire-routing entry points.

This module re-exports symbols with **no wrappers** so call sites keep identical
behavior while the dependency story stays explicit:

* **Document obstacles** live in ``logic_cad.core.obstacles`` (see
  ``obstacles/from_document.py``): axis-aligned rectangles from inserts, wires,
  reserved paths, and port-facing helpers such as ``estimate_port_facing``.
* **Routing search and segment tests** live under ``logic_cad.core.routing``:
  Manhattan routing with escapes, grid snap, and ``path_hits_obstacles`` from
  ``routing/obstacles.py`` (rectangle intersection math on lists produced above—
  not the document builder package ``logic_cad.core.obstacles``).

Wire-service mixins that need both sides may import here instead of splitting
imports across ``obstacles`` and ``routing``. Lower-level tests and algorithms
can continue to import submodules directly.

This module is intentionally **not** re-exported from the
``logic_cad.core.routing`` package root (``routing/__init__.py``) to limit
import-time coupling and avoid cycles.
"""

from __future__ import annotations

from logic_cad.core.obstacles import (
    build_routing_obstacles,
    build_symbol_only_routing_obstacles,
    estimate_port_facing,
    reserved_path_obstacles,
    symbol_obstacles,
    wire_obstacles,
)
from logic_cad.core.routing import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
    dedupe_colinear,
    path_hits_obstacles,
    polyline_segments,
    route_manhattan_with_escape,
    snap_to_grid,
)

__all__ = [
    "DEFAULT_ROUTING_PROFILE",
    "RoutingProfile",
    "build_routing_obstacles",
    "build_symbol_only_routing_obstacles",
    "dedupe_colinear",
    "estimate_port_facing",
    "path_hits_obstacles",
    "polyline_segments",
    "reserved_path_obstacles",
    "route_manhattan_with_escape",
    "snap_to_grid",
    "symbol_obstacles",
    "wire_obstacles",
]
