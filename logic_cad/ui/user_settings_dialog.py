"""Modal dialog for application user preferences (crosshair, etc.)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from logic_cad.ui.app_user_settings import (
    AppUserSettings,
    CROSSHAIR_CENTER_BOX_SIDE_MAX_PX,
    CROSSHAIR_LOCAL_HALF_MAX_PX,
    CROSSHAIR_LOCAL_HALF_MIN_PX,
    CrosshairMode,
)

_USER_SETTINGS_STYLESHEET = """
    QDialog { background-color: #2a2c30; color: #d8d8dc; }
    QLabel { color: #d8d8dc; }
    QComboBox {
        background-color: #3a3c42; color: #e8e8ec; padding: 4px 8px;
        border: 1px solid #4a4f59; border-radius: 2px; min-height: 22px;
        min-width: 280px;
    }
    QComboBox::drop-down { border: none; width: 24px; }
    QComboBox QAbstractItemView {
        background-color: #3a3c42; color: #e8e8ec; selection-background-color: #3d6fb8;
    }
    QSpinBox {
        background-color: #3a3c42; color: #e8e8ec; padding: 4px 8px;
        border: 1px solid #4a4f59; border-radius: 2px; min-height: 22px;
    }
    QSpinBox:disabled { color: #888888; background-color: #2f3136; }
    QDialogButtonBox QPushButton {
        background-color: #3d6fb8; color: #ffffff; padding: 4px 12px;
        border: none; border-radius: 2px;
    }
    QDialogButtonBox QPushButton:hover { background-color: #4a7ec8; }
"""


def run_user_settings_dialog(parent: QWidget | None, current: AppUserSettings) -> AppUserSettings | None:
    """Show user settings; on accept, return values to persist.

    Args:
        parent: Parent widget (typically main window).
        current: Settings currently applied (e.g. from disk).

    Returns:
        New :class:`AppUserSettings` if the user accepted; ``None`` if cancelled.
    """

    dlg = QDialog(parent)
    dlg.setWindowTitle("ユーザ設定")
    dlg.setModal(True)
    dlg.setStyleSheet(_USER_SETTINGS_STYLESHEET)

    root = QVBoxLayout(dlg)

    combo_mode = QComboBox()
    _COMBO_ENTRIES: tuple[tuple[str, CrosshairMode], ...] = (
        ("なし（通常のカーソル）", CrosshairMode.NONE),
        ("画面全体のクロスヘア", CrosshairMode.FULL),
        ("カーソル付近の短いクロスヘア", CrosshairMode.LOCAL),
    )
    for label, mode in _COMBO_ENTRIES:
        combo_mode.addItem(label, mode)

    for i in range(combo_mode.count()):
        if combo_mode.itemData(i) == current.crosshair_mode:
            combo_mode.setCurrentIndex(i)
            break
    else:
        combo_mode.setCurrentIndex(0)

    form = QFormLayout()
    form.addRow("キャンバス上のクロスヘア", combo_mode)
    spin_half = QSpinBox()
    spin_half.setRange(CROSSHAIR_LOCAL_HALF_MIN_PX, CROSSHAIR_LOCAL_HALF_MAX_PX)
    spin_half.setValue(current.crosshair_local_half_extent_px)
    form.addRow("クロスヘア十字の長さ（px）", spin_half)
    spin_box = QSpinBox()
    spin_box.setRange(0, CROSSHAIR_CENTER_BOX_SIDE_MAX_PX)
    spin_box.setValue(current.crosshair_center_box_side_px)
    form.addRow("クロスヘア交点の□サイズ（px、0＝なし）", spin_box)
    root.addLayout(form)

    def _sync_spin_enabled(_index: int = 0) -> None:
        mode = combo_mode.currentData()
        spin_half.setEnabled(mode == CrosshairMode.LOCAL)
        spin_box.setEnabled(mode != CrosshairMode.NONE)

    combo_mode.currentIndexChanged.connect(_sync_spin_enabled)
    _sync_spin_enabled()

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    raw_mode = combo_mode.currentData()
    if isinstance(raw_mode, CrosshairMode):
        mode = raw_mode
    elif isinstance(raw_mode, str):
        try:
            mode = CrosshairMode(raw_mode)
        except ValueError:
            mode = CrosshairMode.NONE
    else:
        mode = CrosshairMode.NONE
    half = spin_half.value()
    box_side = spin_box.value()
    return AppUserSettings(
        crosshair_mode=mode,
        crosshair_local_half_extent_px=half,
        crosshair_center_box_side_px=box_side,
    )
