"""Contraste da paleta (ui/theme.py) segundo o WCAG 2.1: sem Qt, sem tela."""

import pytest

from ui import theme


def _luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_formula_confere_com_valores_conhecidos():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize(("fg", "bg", "minimum"), theme.CONTRAST_PAIRS)
def test_pares_da_interface_atingem_o_minimo(fg, bg, minimum):
    assert contrast(fg, bg) >= minimum, f"{fg} sobre {bg}: {contrast(fg, bg):.2f} < {minimum}"
