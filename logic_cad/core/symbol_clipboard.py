"""In-memory clipboard records for copy/paste of symbols and internal wires."""

from __future__ import annotations

from dataclasses import dataclass, field

from logic_cad.core.model.constants import (
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_CLOUD,
    ENTITY_TYPE_USER_LINE,
    ENTITY_TYPE_USER_TEXT,
    LINETYPE_CONTINUOUS,
)


@dataclass
class UserSketchCopyRecord:
    """LINE / CIRCLE (LD_USER_LINE_* / LD_USER_CIRCLE_*) or TEXT (LD_ANNOTATION) user sketch."""

    entity_type: str
    linetype: str = LINETYPE_CONTINUOUS
    line_start: tuple[float, float] | None = None
    line_end: tuple[float, float] | None = None
    circle_center: tuple[float, float] | None = None
    circle_radius: float = 0.0
    text_insert: tuple[float, float] = (0.0, 0.0)
    text: str = ""
    text_height_mm: float = 4.0
    cloud_points_xyb: list[tuple[float, float, float]] = field(default_factory=list)
    cloud_is_closed: bool = True
    # Stored revcloud pitch + guide outline (LD_APP); None for legacy clipboard rows.
    cloud_pitch_mm: float | None = None
    cloud_guide_vertices: list[tuple[float, float]] | None = None

    def extend_bbox(self, xs: list[float], ys: list[float]) -> None:
        if self.entity_type == ENTITY_TYPE_USER_LINE:
            if self.line_start and self.line_end:
                xs.extend([self.line_start[0], self.line_end[0]])
                ys.extend([self.line_start[1], self.line_end[1]])
        elif self.entity_type == ENTITY_TYPE_USER_CIRCLE:
            if self.circle_center is not None and self.circle_radius > 0:
                cx, cy = self.circle_center
                r = self.circle_radius
                xs.extend([cx - r, cx + r])
                ys.extend([cy - r, cy + r])
        elif self.entity_type == ENTITY_TYPE_USER_TEXT:
            xs.append(self.text_insert[0])
            ys.append(self.text_insert[1])
        elif self.entity_type == ENTITY_TYPE_USER_CLOUD:
            if self.cloud_guide_vertices:
                for x, y in self.cloud_guide_vertices:
                    xs.append(float(x))
                    ys.append(float(y))
            else:
                for x, y, _bulge in self.cloud_points_xyb:
                    xs.append(float(x))
                    ys.append(float(y))


@dataclass
class SymbolCopyRecord:
    source_uid: str
    block_name: str
    insert: tuple[float, float]
    rotation: float
    xscale: float
    yscale: float
    zscale: float
    entity_type: str
    xdata_extra: dict[str, str] = field(default_factory=dict)
    attribs: list[tuple[str, str, int]] = field(default_factory=list)


@dataclass
class WireCopyRecord:
    source_uid: str
    points: list[tuple[float, float]]
    linetype: str
    xdata_extra: dict[str, str] = field(default_factory=dict)


@dataclass
class SymbolClipboardPayload:
    symbols: list[SymbolCopyRecord] = field(default_factory=list)
    wires: list[WireCopyRecord] = field(default_factory=list)
    user_sketches: list[UserSketchCopyRecord] = field(default_factory=list)

    def bbox_min(self) -> tuple[float, float]:
        xs: list[float] = []
        ys: list[float] = []
        for s in self.symbols:
            xs.append(s.insert[0])
            ys.append(s.insert[1])
        for u in self.user_sketches:
            u.extend_bbox(xs, ys)
        if not xs:
            return (0.0, 0.0)
        return (min(xs), min(ys))
