"""Dynamic AND/OR blocks: silk-hat silhouette (4×4 body + left column), 2 mm stubs to port tips."""

from __future__ import annotations

from dataclasses import dataclass

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from logic_cad.core.dxf.text_style import merge_logic_cad_text_style_attrib
from logic_cad.core.model.constants import (
    GATE_STATIC_LABEL_AND,
    GATE_STATIC_LABEL_OR,
    GATE_STATIC_TEXT_HEIGHT_AND_MM,
    GATE_STATIC_TEXT_HEIGHT_OR_MM,
    LAYER_SYMBOL,
    LAYER_TEXT,
    ROUTING_PRE_ENTRY_MM,
)

# Left I/O: stub from x=0 to x=STUB; vertical bar at x=STUB; 4×4 square; output stub to x_out.
STUB_MM = 2.0
PITCH_MM = 2.0
BRIM_MM = 1.0
SQUARE_MM = 4.0

# ATTDEF height (drawing units = mm). Too-small heights look fine in Qt pt preview but tiny in BricsCAD.
GATE_SYM_TEXT_HEIGHT_MM = 0.85
GATE_LABEL0_TEXT_HEIGHT_MM = 0.72


@dataclass(frozen=True)
class GateViewGeometry:
    """Block-local geometry (Y up). Ports at stub tips: IN at x=0, OUT at x_out."""

    xL: float
    xR: float
    x_out: float
    yB: float
    yT: float
    y_sq_B: float
    y_sq_T: float
    mid_y: float
    stub_ys: tuple[float, ...]
    sym_y: float
    input_pre_entry_x: float


def gate_view_geometry_from_block_name(block_name: str) -> GateViewGeometry | None:
    """Return layout for AND_n / OR_n blocks; None if name does not match."""
    bn = block_name.upper()
    if not (bn.startswith("AND_") or bn.startswith("OR_")):
        return None
    try:
        n = int(bn.split("_", 1)[1])
    except ValueError:
        return None
    if n < 1:
        return None
    y_top = n * PITCH_MM + 2.0 * BRIM_MM
    mid_y = y_top / 2.0
    y_sq_B = mid_y - SQUARE_MM / 2.0
    y_sq_T = mid_y + SQUARE_MM / 2.0
    xL = STUB_MM
    xR = xL + SQUARE_MM
    x_out = xR + STUB_MM
    stub_ys = tuple(BRIM_MM + (i + 0.5) * PITCH_MM for i in range(n))
    sym_y = -0.38
    return GateViewGeometry(
        xL=xL,
        xR=xR,
        x_out=x_out,
        yB=0.0,
        yT=y_top,
        y_sq_B=y_sq_B,
        y_sq_T=y_sq_T,
        mid_y=mid_y,
        stub_ys=stub_ys,
        sym_y=sym_y,
        input_pre_entry_x=-ROUTING_PRE_ENTRY_MM,
    )


def _dynamic_gate_block_is_usable(doc: Drawing, name: str) -> bool:
    """True if AND_n/OR_n block has geometry (undo can leave an empty BLOCK record)."""
    blk = doc.blocks.get(name)
    if blk is None:
        return False
    has_sym_attdef = False
    has_out_port = False
    for e in blk:
        if e.dxftype() == "ATTDEF" and str(e.dxf.tag).upper() == "SYM":
            has_sym_attdef = True
        if e.dxftype() == "POINT" and str(e.dxf.layer) == "LD_PORT_OUT0_LOGIC":
            has_out_port = True
    return has_sym_attdef and has_out_port


class DynamicGateFactory:
    def block_name(self, kind: str, n_inputs: int) -> str:
        k = kind.upper()
        if k not in ("AND", "OR"):
            raise ValueError(f"ゲート種別は AND または OR である必要があります（{kind!r}）。")
        return f"{k}_{n_inputs}"

    def ensure_and_block(self, doc: Drawing, n_inputs: int) -> str:
        if n_inputs < 1:
            raise ValueError("入力数 n_inputs は 1 以上である必要があります。")
        name = self.block_name("AND", n_inputs)
        if name in doc.blocks and _dynamic_gate_block_is_usable(doc, name):
            return name
        if name in doc.blocks:
            doc.blocks.delete_block(name)
        self._build_silk_hat_gate(doc, name, n_inputs, static_label=GATE_STATIC_LABEL_AND)
        return name

    def ensure_or_block(self, doc: Drawing, n_inputs: int) -> str:
        if n_inputs < 1:
            raise ValueError("入力数 n_inputs は 1 以上である必要があります。")
        name = self.block_name("OR", n_inputs)
        if name in doc.blocks and _dynamic_gate_block_is_usable(doc, name):
            return name
        if name in doc.blocks:
            doc.blocks.delete_block(name)
        self._build_silk_hat_gate(doc, name, n_inputs, static_label=GATE_STATIC_LABEL_OR)
        return name

    def _build_silk_hat_gate(self, doc: Drawing, name: str, n: int, static_label: str) -> None:
        """Left column grows with n; 4×4 square; 2 mm stubs; connector at stub tips."""
        g = gate_view_geometry_from_block_name(name)
        assert g is not None
        blk = doc.blocks.new(name)

        for i, yi in enumerate(g.stub_ys):
            blk.add_line((0.0, yi), (g.xL, yi), dxfattribs={"layer": LAYER_SYMBOL})
            blk.add_point((0.0, yi), dxfattribs={"layer": f"LD_PORT_IN{i}_LOGIC"})

        blk.add_line((g.xL, g.yB), (g.xL, g.yT), dxfattribs={"layer": LAYER_SYMBOL})

        blk.add_line((g.xL, g.y_sq_B), (g.xR, g.y_sq_B), dxfattribs={"layer": LAYER_SYMBOL})
        blk.add_line((g.xL, g.y_sq_T), (g.xR, g.y_sq_T), dxfattribs={"layer": LAYER_SYMBOL})
        blk.add_line((g.xR, g.y_sq_B), (g.xR, g.y_sq_T), dxfattribs={"layer": LAYER_SYMBOL})

        blk.add_line((g.xR, g.mid_y), (g.x_out, g.mid_y), dxfattribs={"layer": LAYER_SYMBOL})
        blk.add_point((g.x_out, g.mid_y), dxfattribs={"layer": "LD_PORT_OUT0_LOGIC"})

        blk.add_attdef(
            tag="SYM",
            text=name,
            insert=(g.xL + 0.15, g.sym_y),
            height=GATE_SYM_TEXT_HEIGHT_MM,
            dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT}),
        )
        _h_static = (
            GATE_STATIC_TEXT_HEIGHT_AND_MM
            if name.upper().startswith("AND_")
            else GATE_STATIC_TEXT_HEIGHT_OR_MM
        )
        _cx = (g.xL + g.xR) / 2.0
        blk.add_attdef(
            tag="STATIC_LABEL0",
            text=static_label,
            insert=(_cx, g.mid_y),
            height=_h_static,
            dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT}),
        ).set_placement((_cx, g.mid_y), align=TextEntityAlignment.MIDDLE_CENTER)
        blk.add_attdef(
            tag="LABEL0",
            text="",
            insert=(g.xL + 0.2, g.y_sq_B + 0.2),
            height=GATE_LABEL0_TEXT_HEIGHT_MM,
            dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT}),
        )
