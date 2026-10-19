"""
Identidade visual da plataforma: paleta e escala de fonte.

Fonte única dos valores: a QML os lê pela propriedade de contexto `theme`
(as_qml()), e tests/test_theme.py confere o contraste dos pares usados.
Tamanhos em pixels lógicos da tela-alvo (1024 × 600).
"""

from __future__ import annotations

# Paleta. Contraste (WCAG 2.1 AA) conferido em tests/test_theme.py a partir de
# CONTRAST_PAIRS: texto ≥ 4,5:1, contornos e indicadores de componente ≥ 3:1.
BG = "#eef2f9"
TEXT = "#1e2a3a"
MUTED = "#475569"  # texto secundário (6,7:1 sobre BG)
HINT = "#64748b"  # placeholder e texto desabilitado (4,8:1 sobre branco)
CARD = "#ffffff"
BORDER = "#768598"  # contorno de botões, cartões e campos (≥ 3:1 sobre BG e branco)
DIVIDER = "#d8e0ec"  # separadores decorativos (sem papel de componente)
BLUE = "#2563eb"
BLUE_DARK = "#1d4ed8"
GREEN = "#15803d"
GREEN_DARK = "#166534"
RED = "#dc2626"
RED_DARK = "#b91c1c"
FOCUS_RING = "#2563eb"
USER_BUBBLE = "#dbeafe"
AI_BUBBLE = "#f1f5f9"
BLOCK_BG = "#f8fafc"
PRESSED = "#cbd5e1"
DISABLED_BG = "#e2e8f0"
ERROR_BG = "#fef2f2"
ERROR_FG = "#b91c1c"
INFO_BG = "#eff6ff"
INFO_FG = "#1e40af"
SHADE = "#99334155"  # fundo translúcido atrás de diálogos (#AARRGGBB)

# (frente, fundo, mínimo) usados de fato na interface.
CONTRAST_PAIRS: list[tuple[str, str, float]] = [
    (TEXT, BG, 4.5),
    (TEXT, CARD, 4.5),
    (TEXT, USER_BUBBLE, 4.5),
    (TEXT, AI_BUBBLE, 4.5),
    (TEXT, PRESSED, 4.5),
    (MUTED, BG, 4.5),
    (MUTED, CARD, 4.5),
    (MUTED, AI_BUBBLE, 4.5),
    (MUTED, USER_BUBBLE, 4.5),
    (HINT, CARD, 4.5),
    # Botão desabilitado: o WCAG isenta componentes inativos; 3:1 o mantém
    # legível sem parecer que pede ação.
    (HINT, DISABLED_BG, 3.0),
    ("#ffffff", BLUE, 4.5),
    ("#ffffff", BLUE_DARK, 4.5),
    ("#ffffff", GREEN, 4.5),
    ("#ffffff", GREEN_DARK, 4.5),
    ("#ffffff", RED, 4.5),
    ("#ffffff", RED_DARK, 4.5),
    (ERROR_FG, ERROR_BG, 4.5),
    (ERROR_FG, AI_BUBBLE, 4.5),
    (ERROR_FG, CARD, 4.5),
    (INFO_FG, INFO_BG, 4.5),
    (BORDER, BG, 3.0),
    (BORDER, CARD, 3.0),
    (FOCUS_RING, BG, 3.0),
    (FOCUS_RING, CARD, 3.0),
]

# Escala de fonte (px). "tiny" nunca para texto que o aluno precisa ler para agir.
FONT_PX = {"title": 24, "button": 19, "body": 18, "small": 15, "tiny": 14, "mono": 15}

TOUCH_MIN = 48  # lado mínimo de um alvo de toque (px)


def as_qml() -> dict[str, object]:
    """Paleta e medidas com nomes em camelCase, para a QML (`theme.userBubble`)."""
    names = {
        name: value
        for name, value in globals().items()
        if name.isupper() and isinstance(value, str) and value.startswith("#")
    }
    values: dict[str, object] = {_camel(name): value for name, value in names.items()}
    values.update(FONT_PX)
    values["touchMin"] = TOUCH_MIN
    return values


def _camel(name: str) -> str:
    head, *rest = name.lower().split("_")
    return head + "".join(part.capitalize() for part in rest)
