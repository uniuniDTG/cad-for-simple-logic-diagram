"""Resolve the directory that contains Markdown manuals (`docs` at repo root or PyInstaller bundle)."""

from __future__ import annotations

import sys
from pathlib import Path


def docs_directory() -> Path:
    """Return the root folder listing manual `*.md` files.

    In development, this is the repository's top-level ``docs`` directory (sibling of
    the ``logic_cad`` package). When frozen (e.g. PyInstaller), manuals are expected
    under ``sys._MEIPASS / "docs"`` via ``datas``.

    Returns:
        Absolute path to the manuals directory (may or may not exist).

    Raises:
        RuntimeError: If the app is frozen but ``sys._MEIPASS`` is not set.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass is None:
            raise RuntimeError("Frozen runtime requires sys._MEIPASS for bundled docs.")
        return Path(meipass) / "docs"
    return Path(__file__).resolve().parent.parent / "docs"


def docs_dir_exists() -> bool:
    """Return True if the manuals directory exists and is a directory."""
    return docs_directory().is_dir()
