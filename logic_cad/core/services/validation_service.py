"""Facade over dxf_validator + index issues."""

from __future__ import annotations

from ezdxf.document import Drawing

from logic_cad.core.dxf.dxf_validator import validate as validate_doc
from logic_cad.core.model.index_store import IndexStore


class ValidationService:
    def __init__(self, doc: Drawing, index: IndexStore) -> None:
        self.doc = doc
        self.index = index

    def validate(self) -> list[str]:
        issues = validate_doc(self.doc)
        issues.extend(self.index.issues)
        return issues
