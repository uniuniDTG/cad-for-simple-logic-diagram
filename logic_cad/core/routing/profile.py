"""Routing tunables: search limits, gate bundle behavior, relaxed obstacle layers."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from logic_cad.core.model.constants import ROUTING_MAX_SEARCH_STATES

# If set to 0/false/no/off, that routing phase is disabled (see apply_routing_env_overrides).
ENV_ROUTING_FIXED = "LOGIC_CAD_ROUTING_FIXED"
ENV_ROUTING_OVG = "LOGIC_CAD_ROUTING_OVG"


def _env_flag_enabled(raw: str) -> bool:
    """Non-empty env string: truthy unless it looks like a boolean false."""
    return raw.strip().lower() not in ("0", "false", "no", "off")


def apply_routing_env_overrides(profile: RoutingProfile) -> RoutingProfile:
    """Merge LOGIC_CAD_ROUTING_FIXED / LOGIC_CAD_ROUTING_OVG into *profile* (debug / scripts).

    Unset or empty env leaves the corresponding field unchanged.
    """
    kw: dict[str, bool] = {}
    fx = os.environ.get(ENV_ROUTING_FIXED)
    if fx is not None and fx.strip() != "":
        kw["use_fixed_manhattan"] = _env_flag_enabled(fx)
    ox = os.environ.get(ENV_ROUTING_OVG)
    if ox is not None and ox.strip() != "":
        kw["use_ovg_multi"] = _env_flag_enabled(ox)
    if not kw:
        return profile
    return replace(profile, **kw)


@dataclass(frozen=True)
class RoutingProfile:
    max_search_states: int = ROUTING_MAX_SEARCH_STATES  # OVG: max heap pops before abort
    max_escape_candidates: int = 3
    gate_cleanup_pass: bool = True
    # Layers 3–4: retry with symbol-only hard obstacles (may cross existing wires).
    relax_wire_hard_layers: bool = True
    use_fixed_manhattan: bool = True
    use_ovg_multi: bool = True
    # After gate bundle route: swap IN dst_port between crossing wire pairs to reduce crossings.
    enable_and_or_crossing_swaps: bool = False
    # When True (per-wire via replace): route using symbol-only hard obstacles only (may cross wire hulls).
    min_cost_across_wire_obstacle_passes: bool = False


DEFAULT_ROUTING_PROFILE = RoutingProfile()
# Same search budget as DEFAULT; separate name for symbol-move reroute entry (tunable independently later).
FAST_MOVE_REROUTE_PROFILE = RoutingProfile(
    max_search_states=int(ROUTING_MAX_SEARCH_STATES/2),
    max_escape_candidates=3,
    gate_cleanup_pass=True,
    relax_wire_hard_layers=True,
)
