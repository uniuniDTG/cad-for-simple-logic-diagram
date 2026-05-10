"""Optional SYM/LABEL/STATIC_LABEL attribute behavior."""

from logic_cad.core.attrib_tags import list_editable_text_attdef_tags
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.xdata import get_uid


def _add_optional_alarm_block(diagram: LogicDiagram, block_name: str) -> None:
    blk = diagram.doc.blocks.new(block_name)
    blk.add_line((0.0, 0.0), (4.0, 0.0), dxfattribs={"layer": "LD_SYMBOL"})
    blk.add_line((4.0, 0.0), (4.0, 2.0), dxfattribs={"layer": "LD_SYMBOL"})
    blk.add_line((4.0, 2.0), (0.0, 2.0), dxfattribs={"layer": "LD_SYMBOL"})
    blk.add_line((0.0, 2.0), (0.0, 0.0), dxfattribs={"layer": "LD_SYMBOL"})
    blk.add_attdef(tag="STATIC_LABEL0", text="ALARM", insert=(0.2, 2.4), height=0.25)
    blk.add_attdef(tag="LABEL0", text="IN0", insert=(0.2, -0.6), height=0.25)
    blk.add_attdef(tag="LABEL2", text="IN2", insert=(2.2, -0.6), height=0.25)


def test_place_symbol_without_sym_attdef_still_works():
    d = LogicDiagram.new()
    _add_optional_alarm_block(d, "ALARM_OPTIONAL")

    with d.begin("place-alarm"):
        uid = d.place_symbol("ALARM_OPTIONAL", (20.0, 20.0), "ALM1")

    ins = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins is not None
    assert ins.dxf.name == "ALARM_OPTIONAL"
    assert {str(a.dxf.tag) for a in ins.attribs} == set()


def test_optional_symbol_tags_can_be_missing_without_failing_updates():
    d = LogicDiagram.new()
    _add_optional_alarm_block(d, "ALARM_OPTIONAL")

    with d.begin("place-alarm"):
        uid = d.place_symbol("ALARM_OPTIONAL", (20.0, 20.0), "ALM1")

    with d.begin("update-optional-tags"):
        d.set_symbol_attr(uid, "SYM", "ALM1")
        d.set_attrib_visible(uid, "SYM", True)
        d.set_symbol_attr(uid, "LABEL0", "A0")
        d.set_symbol_attr(uid, "LABEL1", "A1")
        d.set_symbol_attr(uid, "LABEL2", "A2")
        d.set_symbol_attr(uid, "STATIC_LABEL0", "ALARM_TEXT")
        d.set_symbol_attr(uid, "STATIC_LABEL1", "ALARM_TEXT_1")

    ins = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins is not None
    attribs = {str(a.dxf.tag): str(a.dxf.text) for a in ins.attribs}
    assert "SYM" not in attribs
    assert attribs["LABEL0"] == "A0"
    assert "LABEL1" not in attribs
    assert attribs["LABEL2"] == "A2"
    assert attribs["STATIC_LABEL0"] == "ALARM_TEXT"
    assert "STATIC_LABEL1" not in attribs


def test_move_insert_rebuilds_attribs_preserves_uid_and_values():
    """Regression: move with ATTRIB must keep LD_APP uid and text (BricsCAD round-trip)."""
    d = LogicDiagram.new()
    with d.begin("place-gate"):
        uid = d.place_and_gate(1, (12.0, 14.0))
    ins0 = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins0 is not None
    assert get_uid(ins0) == uid
    tags0 = {str(a.dxf.tag): str(a.dxf.text) for a in ins0.attribs}
    with d.begin("move-gate"):
        d.symbols.move_insert(d.current_layout_name, uid, (33.0, 44.0))
    ins1 = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins1 is not None
    assert get_uid(ins1) == uid
    assert (float(ins1.dxf.insert.x), float(ins1.dxf.insert.y)) == (33.0, 44.0)
    tags1 = {str(a.dxf.tag): str(a.dxf.text) for a in ins1.attribs}
    assert tags1 == tags0


def test_alarm1_move_preserves_label0_and_editable_tag_values():
    """Optional-attrib symbol: move_insert keeps LABEL*/STATIC_LABEL* (formerly library ALARM1)."""
    d = LogicDiagram.new()
    _add_optional_alarm_block(d, "ALARM_MOVE_REGRESSION")
    with d.begin("place-bell"):
        uid = d.place_symbol("ALARM_MOVE_REGRESSION", (10.0, 20.0), "BELL_1")
    with d.begin("set-labels"):
        d.set_symbol_attr(uid, "LABEL0", "ZONE-A")
        d.set_symbol_attr(uid, "STATIC_LABEL0", "BELL")

    ins0 = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins0 is not None
    block_name = str(ins0.dxf.name)
    tags0 = {str(a.dxf.tag): str(a.dxf.text or "") for a in ins0.attribs}
    assert tags0.get("LABEL0") == "ZONE-A"
    assert tags0.get("STATIC_LABEL0") == "BELL"

    editable = list_editable_text_attdef_tags(d.doc, block_name)
    assert "LABEL0" in editable
    assert "STATIC_LABEL0" in editable

    def values_for_panel(ins) -> dict[str, str]:
        vals: dict[str, str] = {}
        blk = d.doc.blocks.get(block_name)
        for tag in editable:
            want = str(tag).upper()
            val = ""
            for a in ins.attribs:
                if str(a.dxf.tag).upper() == want:
                    val = str(a.dxf.text or "")
                    break
            if not val and blk is not None:
                for ent in blk:
                    if ent.dxftype() == "ATTDEF" and str(ent.dxf.tag).upper() == want:
                        val = str(ent.dxf.text or "")
                        break
            vals[tag] = val
        return vals

    before_panel = values_for_panel(ins0)
    assert before_panel.get("LABEL0") == "ZONE-A"
    assert before_panel.get("STATIC_LABEL0") == "BELL"

    with d.begin("move-bell"):
        d.symbols.move_insert(d.current_layout_name, uid, (55.0, 66.0))

    ins1 = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins1 is not None
    assert (float(ins1.dxf.insert.x), float(ins1.dxf.insert.y)) == (55.0, 66.0)
    tags1 = {str(a.dxf.tag): str(a.dxf.text or "") for a in ins1.attribs}
    assert tags1.get("LABEL0") == "ZONE-A"
    assert tags1.get("STATIC_LABEL0") == "BELL"
    after_panel = values_for_panel(ins1)
    assert after_panel.get("LABEL0") == "ZONE-A"
    assert after_panel.get("STATIC_LABEL0") == "BELL"
