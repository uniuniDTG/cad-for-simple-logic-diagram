"""Tests for layer lineweight dialog color picker behavior."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog

from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui import layer_lineweight_dialog
from logic_cad.ui.layer_lineweight_dialog import _LayerColorSwatchButton


class _AcceptedFakeColorDialog:
    """Fake QColorDialog that accepts and returns a fixed color."""

    ColorDialogOption = layer_lineweight_dialog.QColorDialog.ColorDialogOption
    last_parent: QDialog | None = None
    last_option: tuple[ColorDialogOption, bool] | None = None

    def __init__(self, initial: QColor, parent: QDialog | None = None) -> None:
        """Initialize fake dialog.

        Args:
            initial: Initial color.
            parent: Parent widget passed by caller.
        """
        self._current = QColor(initial)
        self._chosen = QColor(12, 34, 56)
        self.__class__.last_parent = parent

    def setWindowTitle(self, title: str) -> None:
        """Accept title assignment.

        Args:
            title: Dialog title.
        """
        _ = title

    def setCurrentColor(self, color: QColor) -> None:
        """Store current color.

        Args:
            color: Current color value.
        """
        self._current = QColor(color)

    def setOption(self, option: ColorDialogOption, on: bool = True) -> None:
        """Record option assignment.

        Args:
            option: Option enum.
            on: Option state.
        """
        self.__class__.last_option = (option, on)

    def exec(self) -> int:
        """Return accepted status code.

        Returns:
            QDialog accepted code.
        """
        return int(QDialog.DialogCode.Accepted)

    def currentColor(self) -> QColor:
        """Return chosen color.

        Returns:
            Chosen color.
        """
        return QColor(self._chosen)


class _RejectedFakeColorDialog(_AcceptedFakeColorDialog):
    """Fake QColorDialog that behaves as rejected."""

    def exec(self) -> int:
        """Return rejected status code.

        Returns:
            QDialog rejected code.
        """
        return int(QDialog.DialogCode.Rejected)


def test_pick_color_uses_window_parent_and_updates_on_accept(monkeypatch) -> None:
    """Accepted picker uses top-level parent and updates swatch color.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    ensure_qapplication_offscreen()
    host = QDialog()
    button = _LayerColorSwatchButton(QColor(1, 2, 3), host)
    assert button.window() is host

    monkeypatch.setattr(layer_lineweight_dialog, "QColorDialog", _AcceptedFakeColorDialog)
    button._pick_color()

    assert _AcceptedFakeColorDialog.last_parent is host
    assert _AcceptedFakeColorDialog.last_option is not None
    assert _AcceptedFakeColorDialog.last_option[0] == _AcceptedFakeColorDialog.ColorDialogOption.DontUseNativeDialog
    assert _AcceptedFakeColorDialog.last_option[1] is True
    picked = button.color()
    assert (picked.red(), picked.green(), picked.blue()) == (12, 34, 56)


def test_pick_color_keeps_original_on_reject(monkeypatch) -> None:
    """Rejected picker keeps the original swatch color.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    ensure_qapplication_offscreen()
    host = QDialog()
    button = _LayerColorSwatchButton(QColor(7, 8, 9), host)

    monkeypatch.setattr(layer_lineweight_dialog, "QColorDialog", _RejectedFakeColorDialog)
    button._pick_color()

    current = button.color()
    assert (current.red(), current.green(), current.blue()) == (7, 8, 9)
