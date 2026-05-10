"""Structural typing for gate-input wire routing extracted from the mixin."""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.routing.wire_routing_from_document import RoutingProfile


class GateInputWireServiceHost(Protocol):
    """WireService collaboration surface for gate-input routing and optimization.

    Implemented by ``WireServiceGateInputMixin`` plus its sibling mixins (``doc``,
    ``iter_wire_meta``, port geometry helpers, bridge recompute). Keeps extracted
    modules free of concrete ``WireService`` imports.
    """

    doc: Any

    def iter_wire_meta(
        self, layout_name: str
    ) -> Iterator[tuple[Any, str, dict[str, Any]]]:
        """Yield ``(entity, wire_uid, ld_app_dict)`` for WIRE polylines."""

    def _polyline_points(self, entity: Any) -> list[tuple[float, float]]:
        """World polyline vertices for a wire entity."""

    def set_wire_points(
        self,
        layout_name: str,
        entity: Any,
        pts: list[tuple[float, float]],
        *,
        snap_branches: bool = True,
    ) -> None:
        """Persist wire geometry and run post-change hooks."""

    def _symbol_uids_exclude_from_routing_obstacles(
        self, *endpoint_uids: str | None
    ) -> set[str]:
        """Symbol UIDs omitted from hard routing hulls for this route."""

    def _pair_symbol_soft_obstacles(
        self,
        index: IndexStore,
        src_uid: str,
        dst_uid: str,
        access_ports: dict[str, set[str]],
    ) -> list[tuple[float, float, float, float]]:
        """Soft symbol obstacles between two endpoint symbols."""

    def _port_facing(
        self, index: IndexStore, uid: str, port_key: str
    ) -> tuple[int, int] | None:
        """Estimated port facing for Manhattan routing."""

    def _banned_src_cardinals_for_route(
        self,
        layout_name: str,
        src_uid: str,
        src_port: str,
        exclude_wire_uids: set[str] | None = None,
    ) -> Any:
        """Hub OUT cardinals that must not be reused (opaque set or ``None``)."""

    def _gate_input_pre_entry(
        self,
        index: IndexStore,
        gate_uid: str,
        dst_port: str,
        toward: tuple[float, float],
        extra_offset_mm: float = 0.0,
    ) -> tuple[float, float] | None:
        """Pre-entry target toward a gate input port."""

    def _spread_escape_point(
        self,
        src_pt: tuple[float, float],
        escape_pt: tuple[float, float] | None,
        extra_offset_mm: float,
    ) -> tuple[float, float] | None:
        """Offset escape point for bundle spread passes."""

    def _append_port_segment(
        self,
        pts: list[tuple[float, float]],
        port_pt: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Ensure the path terminates on the destination port."""

    def _normalize_auto_route_points(
        self,
        pts: list[tuple[float, float]],
        p0: tuple[float, float],
        p1: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Post-process auto-route polylines."""

    def _route_gate_input_rows(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        n_inputs: int,
        rows: list[tuple[Any, str, str, str, str, int]],
        routing_profile: RoutingProfile | None = None,
    ) -> None:
        """Coordinated multi-wire reroute shared by optimizer and mixin entry points."""

    def _existing_wire_path_segments(
        self,
        layout_name: str,
        exclude_wire_uids: set[str] | None = None,
    ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Other wires' segments for overlap-aware routing."""

    def recompute_all_bridges_ordered(self, layout_name: str) -> None:
        """Rebuild WIRE_BRANCH/CHECKPOINT hulls after geometry changes."""
