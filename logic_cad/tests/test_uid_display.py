from logic_cad.core.uid_display import format_uid_display


def test_format_uid_display_eight_hex():
    u = "550e8400-e29b-41d4-a716-446655440000"
    assert format_uid_display(u) == "550e8400"


def test_format_uid_display_empty():
    assert format_uid_display(None) == "—"
    assert format_uid_display("") == "—"
