"""Tests for application-wide QSettings-backed user preferences."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.app_user_settings import (
    AppUserSettings,
    CrosshairMode,
    CROSSHAIR_CENTER_BOX_SIDE_MAX_PX,
    CROSSHAIR_LOCAL_HALF_MAX_PX,
    CROSSHAIR_LOCAL_HALF_MIN_PX,
    DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX,
    load_app_user_settings,
    save_app_user_settings,
)


def _temp_ini(tmp_path: Path) -> QSettings:
    """Build Ini-format QSettings backed by a unique file under *tmp_path*."""

    path = tmp_path / "user_settings_test.ini"
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_save_load_roundtrip_crosshair(tmp_path: Path) -> None:
    """Persisted crosshair fields reload identically."""

    ensure_qapplication_offscreen()
    s = _temp_ini(tmp_path)
    data = AppUserSettings(
        crosshair_mode=CrosshairMode.FULL,
        crosshair_local_half_extent_px=48,
        crosshair_center_box_side_px=11,
    )
    save_app_user_settings(data, s)
    loaded = load_app_user_settings(s)
    assert loaded == data


def test_legacy_ini_mode_both_maps_to_full(tmp_path: Path) -> None:
    """Older Ini files stored ``both``; load treats that as full-span crosshair."""

    ensure_qapplication_offscreen()
    s = _temp_ini(tmp_path)
    s.beginGroup("crosshair")
    s.setValue("mode", "both")
    s.setValue("local_half_extent_px", 40)
    s.endGroup()
    loaded = load_app_user_settings(s)
    assert loaded.crosshair_mode == CrosshairMode.FULL
    assert loaded.crosshair_local_half_extent_px == 40
    assert loaded.crosshair_center_box_side_px == 0


def test_invalid_mode_string_defaults_to_none(tmp_path: Path) -> None:
    """Unknown ``mode`` value does not crash and maps to ``CrosshairMode.NONE``."""

    ensure_qapplication_offscreen()
    s = _temp_ini(tmp_path)
    s.beginGroup("crosshair")
    s.setValue("mode", "not_a_real_mode")
    s.setValue("local_half_extent_px", 30)
    s.endGroup()
    loaded = load_app_user_settings(s)
    assert loaded.crosshair_mode == CrosshairMode.NONE
    assert loaded.crosshair_local_half_extent_px == 30
    assert loaded.crosshair_center_box_side_px == 0


def test_center_box_side_clamped(tmp_path: Path) -> None:
    """Center pick-box side is clamped to 0..max on load and save."""

    ensure_qapplication_offscreen()
    s = _temp_ini(tmp_path)
    s.beginGroup("crosshair")
    s.setValue("mode", CrosshairMode.LOCAL.value)
    s.setValue("local_half_extent_px", 24)
    s.setValue("center_box_side_px", 9_999)
    s.endGroup()
    assert (
        load_app_user_settings(s).crosshair_center_box_side_px == CROSSHAIR_CENTER_BOX_SIDE_MAX_PX
    )

    lo = AppUserSettings(
        crosshair_mode=CrosshairMode.FULL,
        crosshair_local_half_extent_px=48,
        crosshair_center_box_side_px=-3,
    )
    save_app_user_settings(lo, s)
    assert load_app_user_settings(s).crosshair_center_box_side_px == 0


def test_local_half_extent_clamped(tmp_path: Path) -> None:
    """Out-of-range half extent is clamped on load and on save."""

    ensure_qapplication_offscreen()
    s = _temp_ini(tmp_path)
    s.beginGroup("crosshair")
    s.setValue("mode", CrosshairMode.LOCAL.value)
    s.setValue("local_half_extent_px", 3)
    s.endGroup()
    assert load_app_user_settings(s).crosshair_local_half_extent_px == CROSSHAIR_LOCAL_HALF_MIN_PX

    hi = AppUserSettings(
        crosshair_mode=CrosshairMode.FULL,
        crosshair_local_half_extent_px=9_999,
        crosshair_center_box_side_px=0,
    )
    save_app_user_settings(hi, s)
    assert (
        load_app_user_settings(s).crosshair_local_half_extent_px == CROSSHAIR_LOCAL_HALF_MAX_PX
    )


def test_missing_keys_use_defaults(tmp_path: Path) -> None:
    """Empty Ini yields default mode and default half extent."""

    ensure_qapplication_offscreen()
    s = _temp_ini(tmp_path)
    loaded = load_app_user_settings(s)
    assert loaded.crosshair_mode == CrosshairMode.NONE
    assert loaded.crosshair_local_half_extent_px == DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX
    assert loaded.crosshair_center_box_side_px == 0
