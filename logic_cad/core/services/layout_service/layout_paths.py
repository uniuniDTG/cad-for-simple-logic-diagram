"""Paths to packaged assets and repository root for layout/symbol services."""

from __future__ import annotations

from pathlib import Path


def assets_dir() -> Path:
    """Directory containing ``symbol_library.dxf``, ``frame_template.dxf``, etc.

    Returns:
        ``logic_cad`` package directory joined with ``assets``.
    """
    return Path(__file__).resolve().parents[3] / "assets"


def repo_root() -> Path:
    """Workspace/repository root (parent of the inner ``logic_cad`` package).

    Returns:
        Absolute path to the project root that contains ``generate/frame_template.dxf``.
    """
    return Path(__file__).resolve().parents[4]
