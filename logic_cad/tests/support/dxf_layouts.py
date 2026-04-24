"""DXF layout name helpers for tests."""

from ezdxf.document import Drawing


def first_paper_layout_name(doc: Drawing) -> str:
    """Return the first paper-space layout name in iteration order.

    Args:
        doc: Drawing whose layouts are scanned.

    Returns:
        Name of the first non-modelspace layout.

    Raises:
        ValueError: If there is no paper-space layout.
    """
    for layout in doc.layouts:
        if not layout.is_modelspace:
            return str(layout.name)
    raise ValueError("paper-space layout がありません。")
