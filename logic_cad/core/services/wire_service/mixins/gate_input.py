"""Gate-input routing and AND/OR bundle optimization mixin for ``WireService``.

``route_manhattan_with_escape`` is re-exported on this module so tests can monkeypatch it;
the bundle routing implementation resolves the callable via this module alias to honour patches.
"""

from __future__ import annotations

from typing import Any

from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.routing.wire_routing_from_document import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
    route_manhattan_with_escape,
)
from logic_cad.core.services.wire_service.mixins.gate_input_bundle_routing import (
    route_gate_input_bundle_rows,
)
from logic_cad.core.services.wire_service.mixins.gate_input_crossing_swaps import (
    optimize_and_or_crossing_swaps,
)
from logic_cad.core.services.wire_service.mixins.gate_input_optimize import (
    optimize_and_or_input_ports_impl,
)
from logic_cad.core.services.wire_service.mixins.gate_input_port_assignment import (
    assign_gate_input_ports_by_source_order,
)
from logic_cad.core.services.wire_service.mixins.gate_input_reroute import (
    reroute_gate_input_wire,
)
from logic_cad.core.services.wire_service.mixins.gate_input_rows import (
    collect_gate_input_rows_all,
    gate_input_wire_paths as gate_input_wire_paths_fn,
    gate_input_wire_rows_in_order as gate_input_wire_rows_in_order_fn,
    ordered_gate_inputs_allow_crossing_swaps as ordered_gate_inputs_allow_crossing_swaps_fn,
)


class WireServiceGateInputMixin:
    """Wire routing behaviours specific to symmetric AND/OR inputs."""

    def wire_uses_input_port(self, layout_name: str, gate_uid: str, port_key: str) -> bool:
        """Return whether any ``WIRE`` terminates on ``port_key`` of ``gate_uid``.

        Args:
            layout_name: Active paper-space layout.
            gate_uid: Destination INSERT UID.
            port_key: Full ``IN*_LOGIC`` port key string.

        Returns:
            ``True`` when such a wire exists.
        """
        for _e, _wu, d in self.iter_wire_meta(layout_name):
            if d.get("dst") == gate_uid and d.get("dst_port") == port_key:
                return True
        return False

    def all_and_inputs_wired(self, layout_name: str, gate_uid: str, n_inputs: int) -> bool:
        """Return whether every logical input ``IN0…IN{n-1}`` has at least one wire.

        Args:
            layout_name: Active paper-space layout.
            gate_uid: Dynamic AND/OR ``INSERT``.
            n_inputs: Required input count ``n``.

        Returns:
            ``True`` when every ``IN*_LOGIC`` in the span has at least one wire; otherwise
            ``False``.
        """
        for i in range(n_inputs):
            pk = f"IN{i}_LOGIC"
            if not self.wire_uses_input_port(layout_name, gate_uid, pk):
                return False
        return True

    def first_free_and_input(self, layout_name: str, gate_uid: str, n_inputs: int) -> str | None:
        """Return the first unused ``IN*_LOGIC``, or ``None`` when saturated.

        Args:
            layout_name: Active layout.
            gate_uid: Dynamic AND/OR ``INSERT``.
            n_inputs: Input span.

        Returns:
            The first port key ``IN{i}_LOGIC`` with no terminating wire, or ``None`` when all
            inputs in ``0…n_inputs-1`` are already wired.
        """
        for i in range(n_inputs):
            pk = f"IN{i}_LOGIC"
            if not self.wire_uses_input_port(layout_name, gate_uid, pk):
                return pk
        return None

    def _gate_input_rows_all(
        self, layout_name: str, gate_uid: str
    ) -> list[tuple[Any, str, str, str, str, int]]:
        """Every WIRE into *gate_uid* logic inputs."""
        return collect_gate_input_rows_all(self, layout_name, gate_uid)

    def _gate_input_rows(
        self, layout_name: str, gate_uid: str
    ) -> list[tuple[Any, str, str, str, str, int]]:
        """Gate-input bundle rows (same as all rows into logic inputs)."""
        return self._gate_input_rows_all(layout_name, gate_uid)

    def _assign_gate_input_ports_by_source_order(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        rows: list[tuple[Any, str, str, str, str, int]],
        n_inputs: int,
        reserved_indices: set[int],
    ) -> list[tuple[Any, str, str, str, str, int]] | None:
        """Delegate to :func:`assign_gate_input_ports_by_source_order`."""
        return assign_gate_input_ports_by_source_order(
            index, layout_name, gate_uid, rows, n_inputs, reserved_indices
        )

    def _route_gate_input_rows(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        n_inputs: int,
        rows: list[tuple[Any, str, str, str, str, int]],
        routing_profile: RoutingProfile | None = None,
    ) -> None:
        """Route simultaneous gate-input rows with obstacle sharing and cleanup."""
        route_gate_input_bundle_rows(
            self,
            index,
            layout_name,
            gate_uid,
            n_inputs,
            rows,
            routing_profile=routing_profile,
        )

    def _gate_input_wire_paths(
        self,
        layout_name: str,
        gate_uid: str,
        exclude_wire_uids: set[str] | None = None,
    ) -> list[list[tuple[float, float]]]:
        """Return polylines for wires driven into gate logic inputs."""
        return gate_input_wire_paths_fn(self, layout_name, gate_uid, exclude_wire_uids)

    def _reroute_gate_input_wire(
        self,
        index: IndexStore,
        layout_name: str,
        entity: Any,
        n_inputs: int,
        routing_profile: RoutingProfile | None = None,
    ) -> None:
        """Locally reroute a single wire terminating on a gate input."""
        reroute_gate_input_wire(
            self, index, layout_name, entity, n_inputs, routing_profile=routing_profile
        )

    def _gate_input_wire_rows_in_order(
        self, layout_name: str, gate_uid: str, n: int
    ) -> list[tuple[Any, str, str, str, str, int]] | None:
        """Return rows sorted by assigned IN index when a full permutation is present."""
        return gate_input_wire_rows_in_order_fn(self, layout_name, gate_uid, n)

    def _ordered_gate_inputs_allow_crossing_swaps(
        self, ordered: list[tuple[Any, str, str, str, str, int]] | None
    ) -> bool:
        """Return ``True`` when swap optimization may rewrite crossing inputs."""
        return ordered_gate_inputs_allow_crossing_swaps_fn(ordered)

    def _optimize_and_or_crossing_swaps(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        n: int,
    ) -> None:
        """Greedy pairwise reductions of crossing intersections."""
        optimize_and_or_crossing_swaps(self, index, layout_name, gate_uid, n)

    def optimize_and_or_input_ports(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        routing_profile: RoutingProfile | None = None,
    ) -> bool:
        """Assign connected inputs in heuristic order and route the bundled gate inputs."""
        return optimize_and_or_input_ports_impl(
            self,
            index,
            layout_name,
            gate_uid,
            routing_profile=routing_profile,
        )


__all__ = [
    "DEFAULT_ROUTING_PROFILE",
    "RoutingProfile",
    "WireServiceGateInputMixin",
    "route_gate_input_bundle_rows",
    "route_manhattan_with_escape",
]
