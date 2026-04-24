"""Wire / user-sketch toolbar state synchronized with DiagramScene."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QPushButton

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
        btn_sk_cloud: QPushButton,
        btn_sk_text: QPushButton,
    ) -> None:
        super().__init__()
        self._scene = scene
        self._btn_auto_wire = btn_auto_wire
        self._btn_manual_wire = btn_manual_wire
        self._btn_sk_line = btn_sk_line
        self._btn_sk_circle = btn_sk_circle
        self._btn_sk_cloud = btn_sk_cloud
        self._btn_sk_text = btn_sk_text

    def reset_routing_and_sketch_tools(self) -> None:
        """After new/open: turn off wire and user sketch toggles; sync scene."""
        self._btn_auto_wire.blockSignals(True)
        self._btn_manual_wire.blockSignals(True)
        self._btn_auto_wire.setChecked(False)
        self._btn_manual_wire.setChecked(False)
        self._btn_auto_wire.blockSignals(False)
        self._btn_manual_wire.blockSignals(False)
        self.uncheck_sketch_tools()
        self.sync_wire_scene_from_buttons()

    def clear_wire_routing_tools(self) -> None:
        """Turn off auto/manual wiring when the user clicks a wire while not in wire tools."""
        if not self._btn_auto_wire.isChecked() and not self._btn_manual_wire.isChecked():
            return
        self._btn_auto_wire.blockSignals(True)
        self._btn_manual_wire.blockSignals(True)
        self._btn_auto_wire.setChecked(False)
        self._btn_manual_wire.setChecked(False)
        self._btn_auto_wire.blockSignals(False)
        self._btn_manual_wire.blockSignals(False)
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
        for b in (self._btn_sk_line, self._btn_sk_circle, self._btn_sk_cloud, self._btn_sk_text):
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self._scene.set_user_sketch_tool("none")

    def apply_sketch_tool_to_scene(self) -> None:
        if self._btn_sk_line.isChecked():
            t = "line"
        elif self._btn_sk_circle.isChecked():
            t = "circle"
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
        if snd is self._btn_sk_line and self._btn_sk_line.isChecked():
            self._btn_sk_circle.blockSignals(True)
            self._btn_sk_cloud.blockSignals(True)
            self._btn_sk_text.blockSignals(True)
            self._btn_sk_circle.setChecked(False)
            self._btn_sk_cloud.setChecked(False)
            self._btn_sk_text.setChecked(False)
            self._btn_sk_circle.blockSignals(False)
            self._btn_sk_cloud.blockSignals(False)
            self._btn_sk_text.blockSignals(False)
        elif snd is self._btn_sk_circle and self._btn_sk_circle.isChecked():
            self._btn_sk_line.blockSignals(True)
            self._btn_sk_cloud.blockSignals(True)
            self._btn_sk_text.blockSignals(True)
            self._btn_sk_line.setChecked(False)
            self._btn_sk_cloud.setChecked(False)
            self._btn_sk_text.setChecked(False)
            self._btn_sk_line.blockSignals(False)
            self._btn_sk_cloud.blockSignals(False)
            self._btn_sk_text.blockSignals(False)
        elif snd is self._btn_sk_cloud and self._btn_sk_cloud.isChecked():
            self._btn_sk_line.blockSignals(True)
            self._btn_sk_circle.blockSignals(True)
            self._btn_sk_text.blockSignals(True)
            self._btn_sk_line.setChecked(False)
            self._btn_sk_circle.setChecked(False)
            self._btn_sk_text.setChecked(False)
            self._btn_sk_line.blockSignals(False)
            self._btn_sk_circle.blockSignals(False)
            self._btn_sk_text.blockSignals(False)
        elif snd is self._btn_sk_text and self._btn_sk_text.isChecked():
            self._btn_sk_line.blockSignals(True)
            self._btn_sk_circle.blockSignals(True)
            self._btn_sk_cloud.blockSignals(True)
            self._btn_sk_line.setChecked(False)
            self._btn_sk_circle.setChecked(False)
            self._btn_sk_cloud.setChecked(False)
            self._btn_sk_line.blockSignals(False)
            self._btn_sk_circle.blockSignals(False)
            self._btn_sk_cloud.blockSignals(False)
        if (
            self._btn_sk_line.isChecked()
            or self._btn_sk_circle.isChecked()
            or self._btn_sk_cloud.isChecked()
            or self._btn_sk_text.isChecked()
        ):
            self.clear_wire_routing_tools()
        self.apply_sketch_tool_to_scene()
