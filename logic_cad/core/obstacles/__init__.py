"""Document-derived axis-aligned obstacles for wire routing."""

from logic_cad.core.obstacles.from_document import (
    bbox_uv_to_world_mm,
    branch_center_normalized_in_bbox,
    build_routing_obstacles,
    build_symbol_only_routing_obstacles,
    estimate_port_facing,
    moved_symbols_world_bbox,
    reserved_path_obstacles,
    symbol_obstacles,
    wire_obstacles,
)
from logic_cad.core.obstacles.from_document import _non_attdef_insert_world_bbox

__all__ = [
    "bbox_uv_to_world_mm",
    "branch_center_normalized_in_bbox",
    "build_routing_obstacles",
    "build_symbol_only_routing_obstacles",
    "estimate_port_facing",
    "moved_symbols_world_bbox",
    "reserved_path_obstacles",
    "symbol_obstacles",
    "wire_obstacles",
    "_non_attdef_insert_world_bbox",
]
