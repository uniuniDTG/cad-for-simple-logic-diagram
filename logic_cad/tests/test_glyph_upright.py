"""glyph_upright_extra_deg、_effective_halign、_effective_valign の単体テスト。"""

from logic_cad.ui.block_paint import _effective_halign, _effective_valign, glyph_upright_extra_deg


def test_glyph_upright_180_variants() -> None:
    assert glyph_upright_extra_deg(180.0) == 180.0
    assert glyph_upright_extra_deg(-180.0) == 180.0
    assert glyph_upright_extra_deg(540.0) == 180.0


def test_glyph_upright_not_180() -> None:
    assert glyph_upright_extra_deg(0.0) == 0.0
    assert glyph_upright_extra_deg(90.0) == 0.0
    assert glyph_upright_extra_deg(-90.0) == 0.0
    assert glyph_upright_extra_deg(360.0) == 0.0


class TestEffectiveHalign:
    """_effective_halign: 180° 回転時に left/right(0/2) が反転し、他は不変。"""

    # --- 180° (glyph_extra_deg のみ) ---

    def test_180_left_becomes_right(self) -> None:
        assert _effective_halign(0, 180.0, 0.0) == 2

    def test_180_right2_becomes_left(self) -> None:
        assert _effective_halign(2, 180.0, 0.0) == 0

    def test_180_halign3_unchanged(self) -> None:
        assert _effective_halign(3, 180.0, 0.0) == 3

    def test_180_halign4_unchanged(self) -> None:
        assert _effective_halign(4, 180.0, 0.0) == 4

    def test_180_center_unchanged(self) -> None:
        assert _effective_halign(1, 180.0, 0.0) == 1

    # --- 180° (glyph_extra_deg + rot_deg の合計) ---

    def test_90_plus_90_left_becomes_right(self) -> None:
        # 90 + 90 = 180 → flip
        assert _effective_halign(0, 90.0, 90.0) == 2

    def test_540_normalizes_to_180_left_becomes_right(self) -> None:
        assert _effective_halign(0, 540.0, 0.0) == 2

    def test_neg180_left_becomes_right(self) -> None:
        assert _effective_halign(0, -180.0, 0.0) == 2

    # --- 180° でない角度は変化なし ---

    def test_0_left_unchanged(self) -> None:
        assert _effective_halign(0, 0.0, 0.0) == 0

    def test_0_right_unchanged(self) -> None:
        assert _effective_halign(2, 0.0, 0.0) == 2

    def test_90_left_unchanged(self) -> None:
        assert _effective_halign(0, 90.0, 0.0) == 0

    def test_270_left_unchanged(self) -> None:
        assert _effective_halign(0, 270.0, 0.0) == 0

    def test_360_left_unchanged(self) -> None:
        assert _effective_halign(0, 360.0, 0.0) == 0


class TestEffectiveValign:
    """_effective_valign: 180° 回転時に baseline/top が反転し、middle は不変。"""

    # --- 180° (glyph_extra_deg のみ) ---

    def test_180_baseline_becomes_top(self) -> None:
        assert _effective_valign(0, 180.0, 0.0) == 3

    def test_180_top_becomes_baseline(self) -> None:
        assert _effective_valign(3, 180.0, 0.0) == 0

    def test_180_middle_unchanged(self) -> None:
        assert _effective_valign(2, 180.0, 0.0) == 2

    def test_180_bottom_unchanged(self) -> None:
        assert _effective_valign(1, 180.0, 0.0) == 1

    # --- 180° (glyph_extra_deg + rot_deg の合計) ---

    def test_90_plus_90_baseline_becomes_top(self) -> None:
        # 90 + 90 = 180 → flip
        assert _effective_valign(0, 90.0, 90.0) == 3

    def test_540_normalizes_to_180_baseline_becomes_top(self) -> None:
        assert _effective_valign(0, 540.0, 0.0) == 3

    def test_neg180_baseline_becomes_top(self) -> None:
        assert _effective_valign(0, -180.0, 0.0) == 3

    # --- 180° でない角度は変化なし ---

    def test_0_baseline_unchanged(self) -> None:
        assert _effective_valign(0, 0.0, 0.0) == 0

    def test_0_top_unchanged(self) -> None:
        assert _effective_valign(3, 0.0, 0.0) == 3

    def test_90_baseline_unchanged(self) -> None:
        assert _effective_valign(0, 90.0, 0.0) == 0

    def test_270_baseline_unchanged(self) -> None:
        assert _effective_valign(0, 270.0, 0.0) == 0

    def test_360_baseline_unchanged(self) -> None:
        assert _effective_valign(0, 360.0, 0.0) == 0
