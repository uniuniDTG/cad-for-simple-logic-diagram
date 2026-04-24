"""DXF validator checks for block port definitions."""

from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.dxf.dxf_validator import validate


def test_validate_reports_block_port_definition_gaps_and_duplicates():
    doc = new_document()
    blk = doc.blocks.new("BROKEN_NOT")
    blk.add_point((0.0, 0.0), dxfattribs={"layer": "LD_PORT_IN1_LOGIC"})
    blk.add_point((1.0, 0.0), dxfattribs={"layer": "LD_PORT_OUT0_LOGIC"})
    blk.add_point((2.0, 0.0), dxfattribs={"layer": "LD_PORT_OUT0_LOGIC"})
    blk.add_point((3.0, 0.0), dxfattribs={"layer": "LD_PORT_BAD"})

    issues = validate(doc)

    assert any(
        "BROKEN_NOT" in issue and "ポートレイヤー 'LD_PORT_OUT0_LOGIC' が重複" in issue for issue in issues
    )
    assert any("BROKEN_NOT" in issue and "ポートレイヤー 'LD_PORT_BAD' が不正" in issue for issue in issues)
    assert not any(
        "BROKEN_NOT" in issue
        and (
            "INLOGIC ポートの番号が" in issue
            or "INLOGIC ポートが不足" in issue
            or "INVALUE ポートの番号が" in issue
            or "INVALUE ポートが不足" in issue
            or "INMULTI ポートの番号が" in issue
            or "INMULTI ポートが不足" in issue
        )
        for issue in issues
    )
