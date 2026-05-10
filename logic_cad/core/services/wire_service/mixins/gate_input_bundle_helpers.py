"""Small pure helpers shared by gate-input bundle routing."""

from __future__ import annotations

from logic_cad.core.routing.wire_routing_from_document import RoutingProfile


def fmt_gate_input_pt(pt: tuple[float, float]) -> str:
    """Format a world point for routing logs.

    Args:
        pt: World coordinates in layout units.

    Returns:
        Parenthesized string with one decimal place per axis.
    """
    return f"({pt[0]:.1f},{pt[1]:.1f})"


def routing_profile_summary(p: RoutingProfile) -> str:
    """Human-readable routing profile knob summary for logs.

    Args:
        p: Active routing profile.

    Returns:
        Single-line summary string.
    """
    return (
        f"fixed={p.use_fixed_manhattan} ovg_multi={p.use_ovg_multi} "
        f"relax_hard={p.relax_wire_hard_layers} cleanup={p.gate_cleanup_pass} "
        f"swaps={p.enable_and_or_crossing_swaps} max_states={p.max_search_states}"
    )


def bundle_penalty_score(score: tuple[int, int, int, float]) -> tuple[int, int, int]:
    """Return penalty components used for bundle order pruning.

    Args:
        score: Bundle evaluation score tuple.

    Returns:
        Crossing/overlap/symbol-overlap tuple.
    """
    return score[0], score[1], score[2]


def is_perfect_bundle_score(score: tuple[int, int, int, float]) -> bool:
    """Return whether a bundle score is conflict-free.

    Args:
        score: Bundle evaluation score tuple.

    Returns:
        ``True`` when crossings/overlaps/symbol-overlap are all zero.
    """
    return bundle_penalty_score(score) == (0, 0, 0)
