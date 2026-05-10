"""Contract tests for ``wire_routing_from_document`` re-exports."""

from __future__ import annotations

import logic_cad.core.obstacles as obstacles_pkg
import logic_cad.core.routing as routing_pkg
import logic_cad.core.routing.wire_routing_from_document as wire_routing_from_document


def test_facade_reexports_match_canonical_modules() -> None:
    """Re-exported callables must be identical objects (no wrappers).

    This locks the façade to pure aliases so behavior cannot drift accidentally.
    """
    assert (
        wire_routing_from_document.build_routing_obstacles
        is obstacles_pkg.build_routing_obstacles
    )
    assert (
        wire_routing_from_document.build_symbol_only_routing_obstacles
        is obstacles_pkg.build_symbol_only_routing_obstacles
    )
    assert (
        wire_routing_from_document.estimate_port_facing is obstacles_pkg.estimate_port_facing
    )
    assert (
        wire_routing_from_document.reserved_path_obstacles
        is obstacles_pkg.reserved_path_obstacles
    )
    assert wire_routing_from_document.symbol_obstacles is obstacles_pkg.symbol_obstacles
    assert wire_routing_from_document.wire_obstacles is obstacles_pkg.wire_obstacles

    assert (
        wire_routing_from_document.DEFAULT_ROUTING_PROFILE is routing_pkg.DEFAULT_ROUTING_PROFILE
    )
    assert wire_routing_from_document.RoutingProfile is routing_pkg.RoutingProfile
    assert wire_routing_from_document.dedupe_colinear is routing_pkg.dedupe_colinear
    assert wire_routing_from_document.path_hits_obstacles is routing_pkg.path_hits_obstacles
    assert wire_routing_from_document.polyline_segments is routing_pkg.polyline_segments
    assert (
        wire_routing_from_document.route_manhattan_with_escape
        is routing_pkg.route_manhattan_with_escape
    )
    assert wire_routing_from_document.snap_to_grid is routing_pkg.snap_to_grid


def test_all_exports_documented() -> None:
    """Public façade surface stays explicit."""
    expected = {
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
    }
    assert set(wire_routing_from_document.__all__) == expected
