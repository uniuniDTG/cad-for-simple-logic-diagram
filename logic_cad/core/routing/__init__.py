"""Grid-aligned Manhattan wire routing, obstacle avoidance, and crossing bulges.

**Obstacle naming:** ``logic_cad.core.obstacles`` builds axis-aligned rectangles
from the DXF document. This package's submodule ``routing.obstacles`` tests
segments and polylines against those rectangles (open inflated rectangles).

Submodules: ``profile`` (tunables), ``obstacles`` / ``polyline`` (geometry), ``scoring``,
``facing`` (wraparound hints), ``ovg`` (visibility-graph fallback), ``manhattan`` (main path),
``escape`` (port escape + lane stagger), ``crossings`` (intersections and semijump bulges).

Wire services that need document builders plus these entry points may import
``wire_routing_from_document`` (not re-exported here).
"""

from __future__ import annotations

from .crossings import (
    BULGE_SEMICIRCLE,
    apply_vertical_semijumps_to_xyb,
    horizontal_segment_goes_east,
    orthogonal_segments_crossing_relaxed,
    segments_intersect,
    strip_wire_xyb_semijumps,
)
from .escape import (
    apply_vertical_lane_stagger,
    route_manhattan_with_escape,
)
from .manhattan import route_manhattan
from .obstacles import (
    obstacle_rects_inflated,
    path_hits_obstacle_rects,
    path_hits_obstacles,
    segment_intersects_rect_open,
)
from .polyline import dedupe_colinear, ensure_manhattan_polyline, polyline_segments, snap_to_grid
from .profile import (
    DEFAULT_ROUTING_PROFILE,
    FAST_MOVE_REROUTE_PROFILE,
    RoutingProfile,
)

__all__ = [
    "BULGE_SEMICIRCLE",
    "DEFAULT_ROUTING_PROFILE",
    "FAST_MOVE_REROUTE_PROFILE",
    "RoutingProfile",
    "apply_vertical_lane_stagger",
    "apply_vertical_semijumps_to_xyb",
    "dedupe_colinear",
    "ensure_manhattan_polyline",
    "horizontal_segment_goes_east",
    "obstacle_rects_inflated",
    "orthogonal_segments_crossing_relaxed",
    "path_hits_obstacle_rects",
    "path_hits_obstacles",
    "polyline_segments",
    "route_manhattan",
    "route_manhattan_with_escape",
    "segment_intersects_rect_open",
    "segments_intersect",
    "snap_to_grid",
    "strip_wire_xyb_semijumps",
]
