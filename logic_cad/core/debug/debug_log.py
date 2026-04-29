"""Optional logging helpers for evaluation / troubleshooting.

Default startup level is controlled by ``logic_cad.app.main`` (root logger).
Use ``--debug`` at launch or change level from the log window.

Per-row / per-hop routing chatter (bundle rows, OVG start/no_path/success,
escape traces, bundle vertical_parallel_diag) is enabled at ``DEBUG`` level.

Output routing is provided by Python ``logging`` handlers configured at app startup.
Use ``logic_cad_log_separator`` before a logical batch (e.g. one gate bundle).
"""

from __future__ import annotations

import logging
_LOGIC_CAD_LOGGER = logging.getLogger("logic_cad")


def logic_cad_debug_enabled() -> bool:
    """Whether regular debug logs should be emitted."""
    return _LOGIC_CAD_LOGGER.isEnabledFor(logging.INFO)


def logic_cad_debug_routing_verbose() -> bool:
    """High-volume routing logs (per wire row, OVG layer success, etc.)."""
    return _LOGIC_CAD_LOGGER.isEnabledFor(logging.DEBUG)


def logic_cad_log(tag: str, msg: str) -> None:
    if logic_cad_debug_enabled():
        _LOGIC_CAD_LOGGER.getChild(tag).info(msg)


def logic_cad_log_separator(title: str) -> None:
    """Print a visible break between user actions / routing batches (debug only)."""
    if logic_cad_debug_enabled():
        pad = max(6, (72 - len(title)) // 2)
        line = f"{'-' * pad} {title} {'-' * pad}"
        _LOGIC_CAD_LOGGER.info(line)
