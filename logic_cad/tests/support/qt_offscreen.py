"""Qt offscreen application and diagram rendering for tests."""

import os
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.ui.scene import DiagramScene


def ensure_qapplication_offscreen() -> QApplication:
    """Return a QApplication, creating an offscreen instance if needed.

    Returns:
        Shared ``QApplication`` suitable for headless ``DiagramScene`` rendering.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def render_diagram_to_png(diagram: LogicDiagram, out_path: Path) -> Path:
    """Render the diagram scene to a PNG file (for visual regression / debugging).

    Args:
        diagram: Diagram to render.
        out_path: Output path ending in ``.png``.

    Returns:
        ``out_path`` after a successful save.

    Raises:
        AssertionError: If the image could not be written.
    """
    ensure_qapplication_offscreen()
    scene = DiagramScene(diagram)
    bounds = scene.itemsBoundingRect().adjusted(-12.0, -12.0, 12.0, 12.0)
    if bounds.isEmpty():
        bounds = scene.sceneRect()
    scene.setSceneRect(bounds)
    scale = 6.0
    width = max(1, int(bounds.width() * scale))
    height = max(1, int(bounds.height() * scale))
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(24, 24, 24))
    painter = QPainter(image)
    scene.render(painter, QRectF(0.0, 0.0, float(width), float(height)), bounds)
    painter.end()
    assert image.save(str(out_path))
    return out_path


def png_output_path_for_test(tmp_path: Path, filename: str) -> Path:
    """Resolve PNG path: ``LOGIC_CAD_TEST_RENDER_OUT`` or ``tmp_path / filename``."""
    override = os.environ.get("LOGIC_CAD_TEST_RENDER_OUT")
    if override:
        return Path(override)
    return tmp_path / filename
