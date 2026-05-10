"""Helpers for checkable tool buttons: silent updates and exclusive groups.

Qt ``QAbstractButton`` toggles emit ``toggled`` while the checked state changes.
Mutual-exclusion and bulk resets keep ``blockSignals(True)`` around ``setChecked``
so UI code can update several buttons atomically before handlers run.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QAbstractButton


def set_buttons_checked_silently(
    buttons: Sequence[QAbstractButton],
    checked: bool,
) -> None:
    """Set ``checked`` on each button without emitting ``toggled`` / ``clicked``.

    All given buttons are blocked first, then updated, then unblocked. That matches
    the common pattern of turning off a wire-tool pair (or a sketch-tool row) in one
    step so no slot observes an intermediate mixed state.

    Args:
        buttons: Buttons to update (typically checkable ``QPushButton`` tools).
        checked: Target checked state (usually ``False`` for reset / exclusive-off).

    Returns:
        None
    """
    blocked: list[QAbstractButton] = []
    try:
        for b in buttons:
            b.blockSignals(True)
            blocked.append(b)
        for b in blocked:
            b.setChecked(checked)
    finally:
        for b in blocked:
            b.blockSignals(False)


def uncheck_buttons_except(
    group: Sequence[QAbstractButton],
    keep: QAbstractButton,
) -> None:
    """Uncheck every member of ``group`` except ``keep`` (identity), silently.

    Used for "exactly one placement/sketch tool checked": the sender stays checked;
    the rest are cleared without firing their ``toggled`` handlers.

    Args:
        group: All mutually exclusive tool buttons (inclusive of ``keep``).
        keep: The button that should remain in its current checked state.

    Returns:
        None
    """
    others = [b for b in group if b is not keep]
    set_buttons_checked_silently(others, False)
