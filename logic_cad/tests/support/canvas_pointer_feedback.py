"""Shared helpers for canvas pointer-feedback performance logic."""

from __future__ import annotations

from logic_cad.ui.scene_item.osnap import OsnapCandidate


def osnap_candidate_key(cand: OsnapCandidate | None) -> tuple[object, ...] | None:
    """Mirror DiagramScene._osnap_candidate_key for unit tests."""
    if cand is None:
        return None
    return (
        cand.kind,
        round(float(cand.dxf_pos[0]), 4),
        round(float(cand.dxf_pos[1]), 4),
        cand.symbol_uid,
        cand.port_key,
    )
