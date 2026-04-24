"""Optional stdout logging for evaluation / troubleshooting.

Disabled by default. Enable all tagged logs:

    set LOGIC_CAD_DEBUG=1

Or launch with:

    python -m logic_cad.app.main --debug

Per-row / per-hop routing chatter (bundle rows, OVG start/no_path/success, escape traces,
bundle vertical_parallel_diag) requires additionally:

    set LOGIC_CAD_DEBUG_ROUTING_VERBOSE=1

Each line is prefixed with local time (HH:MM:SS.mmm) for correlation. Use
``logic_cad_log_separator`` before a logical batch (e.g. one gate bundle).

(Search for \"[logic_cad:\" or logic_cad_log to remove or gate later.)
"""

from __future__ import annotations

import os
from datetime import datetime


def logic_cad_debug_enabled() -> bool:
    v = os.environ.get("LOGIC_CAD_DEBUG", "")
    return v.strip().lower() in ("1", "true", "yes", "on")


def logic_cad_debug_routing_verbose() -> bool:
    """High-volume routing logs (per wire row, OVG layer success, etc.)."""
    if not logic_cad_debug_enabled():
        return False
    v = os.environ.get("LOGIC_CAD_DEBUG_ROUTING_VERBOSE", "")
    return v.strip().lower() in ("1", "true", "yes", "on")


def _logic_cad_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def logic_cad_log(tag: str, msg: str) -> None:
    if logic_cad_debug_enabled():
        print(f"[{_logic_cad_timestamp()}] [logic_cad:{tag}] {msg}", flush=True)


def logic_cad_log_separator(title: str) -> None:
    """Print a visible break between user actions / routing batches (debug only)."""
    if logic_cad_debug_enabled():
        pad = max(6, (72 - len(title)) // 2)
        line = f"{'-' * pad} {title} {'-' * pad}"
        print(f"[{_logic_cad_timestamp()}] [logic_cad] {line}", flush=True)
