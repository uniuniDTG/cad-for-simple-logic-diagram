from __future__ import annotations

from logic_cad.core.model.xdata import get_type
from logic_cad.core.model.constants import ENTITY_TYPE_WIRE_BRANCH


class WireServiceBranchMixin:
    def remove_wire_branch(self, layout_name: str, branch_uid: str) -> set[str | None]:
        """Delete INSERT WIRE_BRANCH and every WIRE incident to it."""
        from logic_cad.core.undo.history import find_entity_by_uid

        e = find_entity_by_uid(self.doc, branch_uid)
        if e is None or e.dxftype() != "INSERT" or get_type(e) != ENTITY_TYPE_WIRE_BRANCH:
            return set()
        touched: set[str | None] = set()
        for ent, _wu, d in list(self.iter_wire_meta(layout_name)):
            if d.get("src") == branch_uid or d.get("dst") == branch_uid:
                touched.add(d.get("src"))
                touched.add(d.get("dst"))
                self.doc.entitydb.delete_entity(ent)
        if e.is_alive:
            self.doc.entitydb.delete_entity(e)
        return touched
