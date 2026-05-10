"""Wire / user-sketch toolbar state synchronized with DiagramScene."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QPushButton

from logic_cad.ui.exclusive_tool_buttons import (
    set_buttons_checked_silently,
    uncheck_buttons_except,
)

if TYPE_CHECKING:
    from logic_cad.ui.scene import DiagramScene


class WireSketchToolBridge(QObject):
    def __init__(
        self,
        scene: DiagramScene,
        btn_auto_wire: QPushButton,
        btn_manual_wire: QPushButton,
        btn_sk_line: QPushButton,
        btn_sk_circle: QPushButton,
        btn_sk_arc: QPushButton,
        btn_sk_cloud: QPushButton,
        btn_sk_text: QPushButton,
    ) -> None:
        super().__init__()
        self._scene = scene
        self._btn_auto_wire = btn_auto_wire
        self._btn_manual_wire = btn_manual_wire
        self._btn_sk_line = btn_sk_line
        self._btn_sk_circle = btn_sk_circle
        self._btn_sk_arc = btn_sk_arc
        self._btn_sk_cloud = btn_sk_cloud
        self._btn_sk_text = btn_sk_text
        self._sketch_tool_buttons: tuple[QPushButton, ...] = (
            btn_sk_line,
            btn_sk_circle,
            btn_sk_arc,
            btn_sk_cloud,
            btn_sk_text,
        )

    def connect_toolbar_signals(self) -> None:
        """Connect ``toggled`` from wire/sketch toolbar buttons to bridge slots.

        Keeps :class:`MainWindow` wiring minimal; behavior matches previous
        per-button ``connect`` calls in the window constructor.

        Note:
            Call this **exactly once**, typically from ``MainWindow.__init__``.
            Invoking it again adds extra ``toggled`` connections, so each toggle
            fires the handlers multiple times (duplicate side effects).

        Returns:
            None
        """
        self._btn_auto_wire.toggled.connect(self.on_auto_wire_toggled)
        self._btn_manual_wire.toggled.connect(self.on_manual_wire_toggled)
        self._btn_sk_line.toggled.connect(self.on_any_sketch_toggled)
        self._btn_sk_circle.toggled.connect(self.on_any_sketch_toggled)
        self._btn_sk_arc.toggled.connect(self.on_any_sketch_toggled)
        self._btn_sk_cloud.toggled.connect(self.on_any_sketch_toggled)
        self._btn_sk_text.toggled.connect(self.on_any_sketch_toggled)

    def reset_routing_and_sketch_tools(self) -> None:
        """After new/open: turn off wire and user sketch toggles; sync scene."""
        set_buttons_checked_silently((self._btn_auto_wire, self._btn_manual_wire), False)
        self.uncheck_sketch_tools()
        self.sync_wire_scene_from_buttons()

    def clear_wire_routing_tools(self) -> None:
        """Turn off auto/manual wiring when the user clicks a wire while not in wire tools."""
        if not self._btn_auto_wire.isChecked() and not self._btn_manual_wire.isChecked():
            return
        set_buttons_checked_silently((self._btn_auto_wire, self._btn_manual_wire), False)
        self.sync_wire_scene_from_buttons()

    def sync_wire_scene_from_buttons(self) -> None:
        """Scene wire_mode is on if either auto or manual tool is checked."""
        auto = self._btn_auto_wire.isChecked()
        manual = self._btn_manual_wire.isChecked()
        if auto or manual:
            self.uncheck_sketch_tools()
        self._scene.set_manual_wire_mode(manual)
        self._scene.set_wire_mode(auto or manual)

    def on_auto_wire_toggled(self, checked: bool) -> None:
        _ = checked
        self.sync_wire_scene_from_buttons()

    def on_manual_wire_toggled(self, checked: bool) -> None:
        _ = checked
        self.sync_wire_scene_from_buttons()

    def uncheck_sketch_tools(self) -> None:
        """Turn off all user-sketch toggles; set scene sketch tool to ``none``."""
        set_buttons_checked_silently(self._sketch_tool_buttons, False)
        self._scene.set_user_sketch_tool("none")

    def apply_sketch_tool_to_scene(self) -> None:
        if self._btn_sk_line.isChecked():
            t = "line"
        elif self._btn_sk_circle.isChecked():
            t = "circle"
        elif self._btn_sk_arc.isChecked():
            t = "arc"
        elif self._btn_sk_cloud.isChecked():
            t = "cloud"
        elif self._btn_sk_text.isChecked():
            t = "text"
        else:
            t = "none"
        self._scene.set_user_sketch_tool(t)

    def on_any_sketch_toggled(self, checked: bool) -> None:
        _ = checked
        snd = self.sender()
        if (
            isinstance(snd, QPushButton)
            and snd in self._sketch_tool_buttons
            and snd.isChecked()
        ):
            uncheck_buttons_except(self._sketch_tool_buttons, snd)
        if any(b.isChecked() for b in self._sketch_tool_buttons):
            self.clear_wire_routing_tools()
        self.apply_sketch_tool_to_scene()
