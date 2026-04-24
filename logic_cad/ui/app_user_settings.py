"""Application-wide user preferences (not stored in DXF).

Persistence uses :class:`PySide6.QtCore.QSettings` with Ini format so the on-disk
file is human-editable. Call :func:`crosshair_settings` for the default scope tied to
:func:`PySide6.QtWidgets.QApplication.setOrganizationName` / ``setApplicationName``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QSettings

# Must match values passed to QApplication in ``logic_cad.app.main`` so Ini path is stable.
APP_ORG_NAME = "LogicCAD"
APP_DISPLAY_NAME = "Logic CAD"

_SETTINGS_GROUP_CROSSHAIR = "crosshair"
_KEY_CROSSHAIR_MODE = "mode"
_KEY_LOCAL_HALF_EXTENT_PX = "local_half_extent_px"
_KEY_CENTER_BOX_SIDE_PX = "center_box_side_px"

DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX = 24
CROSSHAIR_LOCAL_HALF_MIN_PX = 8
CROSSHAIR_LOCAL_HALF_MAX_PX = 200

DEFAULT_CROSSHAIR_CENTER_BOX_SIDE_PX = 0
CROSSHAIR_CENTER_BOX_SIDE_MAX_PX = 64


class CrosshairMode(StrEnum):
    """How the diagram view draws the cursor crosshair overlay (viewport pixels)."""

    NONE = "none"
    FULL = "full"
    LOCAL = "local"


# Stored as ``both`` in older Ini files; load maps this to :attr:`CrosshairMode.FULL`.
_LEGACY_CROSSHAIR_MODE_BOTH_VALUE = "both"


@dataclass(frozen=True)
class AppUserSettings:
    """User preferences loaded at startup and from the settings dialog.

    Attributes:
        crosshair_mode: Crosshair overlay mode for the main diagram view.
        crosshair_local_half_extent_px: Half-length in pixels for local arms (``local`` only).
        crosshair_center_box_side_px: Pick-style hollow square at crosshair center (0 = draw lines only).
    """

    crosshair_mode: CrosshairMode
    crosshair_local_half_extent_px: int
    crosshair_center_box_side_px: int = DEFAULT_CROSSHAIR_CENTER_BOX_SIDE_PX


def crosshair_settings() -> QSettings:
    """Return Ini-backed settings for the running application (default file location).

    PySide6 requires ``(format, scope, organization, application)`` for Ini storage;
    values must match ``logic_cad.app.main`` so reads/writes hit the same file.

    Returns:
        QSettings instance scoped by organization and application name.
    """

    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        APP_ORG_NAME,
        APP_DISPLAY_NAME,
    )


def _clamp_half_px(value: int) -> int:
    return max(CROSSHAIR_LOCAL_HALF_MIN_PX, min(CROSSHAIR_LOCAL_HALF_MAX_PX, value))


def _clamp_center_box_side_px(value: int) -> int:
    return max(0, min(CROSSHAIR_CENTER_BOX_SIDE_MAX_PX, value))


def _parse_crosshair_mode(raw: object) -> CrosshairMode:
    if isinstance(raw, str) and raw:
        if raw == _LEGACY_CROSSHAIR_MODE_BOTH_VALUE:
            return CrosshairMode.FULL
        try:
            return CrosshairMode(raw)
        except ValueError:
            pass
    return CrosshairMode.NONE


def load_app_user_settings(settings: QSettings | None = None) -> AppUserSettings:
    """Read crosshair options from *settings* (or the default app Ini file).

    Args:
        settings: Optional QSettings (e.g. temp file in tests).

    Returns:
        Parsed :class:`AppUserSettings`; invalid stored values fall back to safe defaults.
    """

    s = settings if settings is not None else crosshair_settings()
    s.beginGroup(_SETTINGS_GROUP_CROSSHAIR)
    mode = _parse_crosshair_mode(s.value(_KEY_CROSSHAIR_MODE, CrosshairMode.NONE.value))
    half_raw = s.value(_KEY_LOCAL_HALF_EXTENT_PX, DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX)
    box_raw = s.value(_KEY_CENTER_BOX_SIDE_PX, DEFAULT_CROSSHAIR_CENTER_BOX_SIDE_PX)
    s.endGroup()
    try:
        half = int(half_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        half = DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX
    try:
        box_side = int(box_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        box_side = DEFAULT_CROSSHAIR_CENTER_BOX_SIDE_PX
    return AppUserSettings(
        crosshair_mode=mode,
        crosshair_local_half_extent_px=_clamp_half_px(half),
        crosshair_center_box_side_px=_clamp_center_box_side_px(box_side),
    )


def save_app_user_settings(data: AppUserSettings, settings: QSettings | None = None) -> None:
    """Persist crosshair options to *settings* (or the default app Ini file).

    Args:
        data: Values to store.
        settings: Optional QSettings (e.g. temp file in tests).

    Returns:
        None
    """

    s = settings if settings is not None else crosshair_settings()
    s.beginGroup(_SETTINGS_GROUP_CROSSHAIR)
    s.setValue(_KEY_CROSSHAIR_MODE, data.crosshair_mode.value)
    s.setValue(
        _KEY_LOCAL_HALF_EXTENT_PX,
        _clamp_half_px(data.crosshair_local_half_extent_px),
    )
    s.setValue(
        _KEY_CENTER_BOX_SIDE_PX,
        _clamp_center_box_side_px(data.crosshair_center_box_side_px),
    )
    s.endGroup()
    s.sync()
