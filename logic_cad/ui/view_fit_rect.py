"""Scene-coordinate rectangles for default diagram sheet framing (mm units)."""

from __future__ import annotations

from PySide6.QtCore import QRectF

from logic_cad.core.model.constants import A4_LANDSCAPE_HEIGHT_MM, A4_LANDSCAPE_WIDTH_MM

# Margin passed to :func:`default_a4_fit_rect_mm` must stay aligned with
# :meth:`logic_cad.ui.views.diagram_view.DiagramView.fit_a4_page`.
DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM = 12.0


def default_a4_fit_rect_mm(margin_mm: float = DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM) -> QRectF:
    """Return the landscape A4 sheet rectangle used by the main diagram view reset.

    Scene coordinates follow DXF→scene mapping (y downward): the sheet spans
    ``x ∈ [0, W]`` and ``y_scene ∈ [-H, 0]`` before margin expansion.

    Args:
        margin_mm: Uniform expansion on all sides in millimetres.

    Returns:
        Axis-aligned rectangle enclosing the sheet plus margin.
    """

    m = float(margin_mm)
    return QRectF(
        -m,
        -A4_LANDSCAPE_HEIGHT_MM - m,
        A4_LANDSCAPE_WIDTH_MM + 2 * m,
        A4_LANDSCAPE_HEIGHT_MM + 2 * m,
    )
