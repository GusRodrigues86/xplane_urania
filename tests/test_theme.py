import re

import pytest

from urania import theme


@pytest.mark.parametrize("fg,bg", theme.TEXT_PAIRS)
def test_wcag_aa_contrast(fg, bg):
    ratio = theme.contrast(theme.TOKENS[fg], theme.TOKENS[bg])
    assert ratio >= 4.5, f"{fg} on {bg}: {ratio:.2f} < 4.5 (WCAG AA)"


def test_tokens_are_hex_colors():
    for name, value in theme.TOKENS.items():
        assert re.fullmatch(r"#[0-9A-F]{6}", value), name


def test_uranus_palette_is_cyan():
    # Uranus in visible light: blue-green, little red.
    r, g, b = theme.hex_to_rgb(theme.TOKENS["primary"])
    assert g > r and b > r


def test_mix_and_contrast():
    assert theme.mix("#000000", "#FFFFFF", 0.5) in ("#7F7F7F", "#808080")
    assert theme.contrast("#000000", "#FFFFFF") == pytest.approx(21.0)


def test_starfield_is_stable():
    a = theme.starfield(800, 120, 50)
    assert a == theme.starfield(800, 120, 50)
    assert all(0 <= x <= 800 and 0 <= y <= 120 for x, y, _, _ in a)


def test_uranus_rings_go_inward():
    rings = theme.uranus_rings(30)
    radii = [r for r, _ in rings]
    assert radii == sorted(radii, reverse=True)
    assert rings[0][1] == theme.TOKENS["primary_deep"]
