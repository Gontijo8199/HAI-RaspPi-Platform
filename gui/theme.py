"""
Identidade visual da POC (POC/interface.zip → estilo.css), adaptada ao Tk.

Tamanhos são definidos em PIXELS da tela-alvo (1024×600, como no CSS) e
convertidos para pontos com a escala real do Tk, para ficarem iguais em
monitores com DPI diferente.

Sem emoji: o Tk 8.6 no X11 não desenha fontes de emoji coloridas (e algumas
derrubam a conexão com o X). Ícones são símbolos do plano básico Unicode ou
desenhados em Canvas.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont

# Paleta (estilo.css + conversar-llm.html)
BG = "#eef2f9"
TEXT = "#1e2a3a"
MUTED = "#64748b"
HINT = "#94a3b8"
CARD = "#ffffff"
BORDER = "#d8e0ec"
BLUE = "#3b82f6"
BLUE_DARK = "#2563eb"
GREEN = "#22c55e"
GREEN_DARK = "#16a34a"
RED = "#ef4444"
RED_DARK = "#dc2626"
USER_BUBBLE = "#dbeafe"
AI_BUBBLE = "#f1f5f9"
BLOCK_BG = "#f8fafc"
REMOVE_BG = "#fee2e2"
REMOVE_FG = "#b91c1c"
INSERT_BG = "#e2e8f0"
ERROR_BG = "#fef2f2"
ERROR_FG = "#b91c1c"
INFO_BG = "#eff6ff"
INFO_FG = "#1e40af"

REFERENCE_SIZE = (1024, 600)

_FAMILIES = ("DejaVu Sans", "Noto Sans", "Liberation Sans", "Helvetica")
_MONO_FAMILIES = ("DejaVu Sans Mono", "Noto Sans Mono", "Liberation Mono", "Courier")


@dataclass(frozen=True)
class Fonts:
    title: tkfont.Font
    button: tkfont.Font
    body: tkfont.Font
    body_bold: tkfont.Font
    small: tkfont.Font
    tiny: tkfont.Font
    mono: tkfont.Font


def _pick(root: tk.Misc, candidates: tuple[str, ...]) -> str:
    available = set(tkfont.families(root))
    return next((f for f in candidates if f in available), "TkDefaultFont")


def make_fonts(root: tk.Misc) -> Fonts:
    family = _pick(root, _FAMILIES)
    mono = _pick(root, _MONO_FAMILIES)
    px_per_pt = max(root.winfo_fpixels("1i") / 72.0, 0.5)

    def font(px: int, weight: str = "normal", fam: str = family) -> tkfont.Font:
        return tkfont.Font(root=root, family=fam, size=max(round(px / px_per_pt), 6), weight=weight)

    return Fonts(
        title=font(26, "bold"),
        button=font(19, "bold"),
        body=font(17),
        body_bold=font(17, "bold"),
        small=font(15),
        tiny=font(13),
        mono=font(15, fam=mono),
    )


def fonts_for(widget: tk.Misc) -> Fonts:
    """Fontes da janela de `widget`, criadas uma vez por janela (não a cada tela)."""
    root = widget.winfo_toplevel()
    fonts = getattr(root, "_hai_fonts", None)
    if fonts is None:
        fonts = make_fonts(root)
        root._hai_fonts = fonts
    return fonts
