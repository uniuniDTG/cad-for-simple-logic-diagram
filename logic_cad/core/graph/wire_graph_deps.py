"""Shared callbacks for port / hub graph logic (see :mod:`port_src_dst_solver`).

The solver intentionally stays free of ``Drawing`` / ``WireService`` imports; callers
bundle the two capabilities that tie XDATA to document state here so we do not
thread the same pair of callables through every call site.

TODO: If tests need lighter fakes, consider a ``Protocol`` with these two callables
      plus ``is_wire_hub`` instead of concrete ``WireGraphDeps`` everywhere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from logic_cad.core.model.constants import ENTITY_TYPE_CHECKPOINT, ENTITY_TYPE_WIRE_BRANCH


@dataclass(frozen=True, slots=True)
class WireGraphDeps:
    """Document-backed view needed to interpret wire metadata as a graph."""

    iter_wire_meta: Callable[[str], Iterator[tuple[object, str, dict]]]
    symbol_entity_type_fn: Callable[[str], str | None]

    def is_wire_hub(self, uid: str) -> bool:
        # Same notion as ``is_hub_type(symbol_entity_type_fn(uid))`` in the solver;
        # kept inline to avoid importing solver helpers from this tiny bundle module.
        t = self.symbol_entity_type_fn(uid)
        return t in (ENTITY_TYPE_WIRE_BRANCH, ENTITY_TYPE_CHECKPOINT)
