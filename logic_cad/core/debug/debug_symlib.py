"""Optional logging for symbol library and palette.

Disable by default. To enable either:

    python -m logic_cad.app.main --debug
    set LOGIC_CAD_DEBUG_SYMLIB=1

(Search codebase for [symlib] or symlib_log to remove later.)
"""

from __future__ import annotations

import logging
import os

from logic_cad.core.debug.debug_log import logic_cad_debug_enabled

_SYMLIB_LOGGER = logging.getLogger("logic_cad.symlib")


def symlib_debug_enabled() -> bool:
    """Whether symbol-library logs should be emitted."""
    if logic_cad_debug_enabled():
        return True
    v = os.environ.get("LOGIC_CAD_DEBUG_SYMLIB", "")
    return v.strip().lower() in ("1", "true", "yes", "on")


def symlib_log(msg: str) -> None:
    if symlib_debug_enabled():
        _SYMLIB_LOGGER.info(msg)
