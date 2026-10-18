"""
Renderização de Markdown (display/markdown_parser.py) num widget tk.Text.

Compartilhado pela janela do modo terminal (display/markdown_display.py,
tema escuro) e pelos balões de resposta do módulo de conversa (tema claro).
Não importa tkinter: recebe o widget pronto, então o parser segue testável
sem servidor X.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from display.markdown_parser import parse_markdown


@dataclass(frozen=True)
class MarkdownColors:
    code_bg: str = "#333333"
    code_block_bg: str = "#111111"
    quote_fg: str = "#9fb3c8"
    quote_marker_fg: str = "#5a7a9a"
    bullet_fg: str = "#7fb0ff"
    hr_fg: str = "#555555"


DARK = MarkdownColors()
LIGHT = MarkdownColors(
    code_bg="#e2e8f0",
    code_block_bg="#e2e8f0",
    quote_fg="#475569",
    quote_marker_fg="#94a3b8",
    bullet_fg="#3b82f6",
    hr_fg="#cbd5e1",
)


def configure_tags(
    widget: Any, body_font: Any, mono_font: Any, colors: MarkdownColors = DARK
) -> None:
    base_size = body_font.cget("size")
    family = body_font.cget("family")

    for level, delta in ((1, 8), (2, 5), (3, 2), (4, 0), (5, -2), (6, -2)):
        widget.tag_configure(
            f"h{level}",
            font=(family, base_size + delta, "bold"),
            spacing3=6,
        )
    widget.tag_configure("bold", font=(family, base_size, "bold"))
    widget.tag_configure("italic", font=(family, base_size, "italic"))
    widget.tag_configure(
        "code",
        font=(mono_font.cget("family"), mono_font.cget("size")),
        background=colors.code_bg,
    )
    widget.tag_configure(
        "code_block",
        font=(mono_font.cget("family"), mono_font.cget("size")),
        background=colors.code_block_bg,
        lmargin1=16,
        lmargin2=16,
        spacing1=4,
        spacing3=4,
    )
    widget.tag_configure("quote", foreground=colors.quote_fg, font=(family, base_size, "italic"))
    widget.tag_configure("quote_marker", foreground=colors.quote_marker_fg)
    widget.tag_configure("bullet_marker", foreground=colors.bullet_fg)
    widget.tag_configure("hr", foreground=colors.hr_fg)


def render(widget: Any, markdown_text: str) -> None:
    """Substitui o conteúdo do widget pelo Markdown renderizado."""
    blocks = parse_markdown(markdown_text)
    widget.configure(state="normal")
    widget.delete("1.0", "end")

    for block in blocks:
        btype = block.type
        if btype == "blank":
            widget.insert("end", "\n")
        elif btype == "hr":
            widget.insert("end", "─" * 36 + "\n", ("hr",))
        elif btype == "code_block":
            widget.insert("end", block.text + "\n", ("code_block",))
        elif btype == "heading":
            for run in block.runs:
                widget.insert("end", run.text, (f"h{block.level}", *run.tags))
            widget.insert("end", "\n")
        elif btype == "bullet":
            widget.insert("end", "• ", ("bullet_marker",))
            for run in block.runs:
                widget.insert("end", run.text, run.tags)
            widget.insert("end", "\n")
        elif btype == "numbered":
            widget.insert("end", f"{block.index}. ", ("bullet_marker",))
            for run in block.runs:
                widget.insert("end", run.text, run.tags)
            widget.insert("end", "\n")
        elif btype == "quote":
            widget.insert("end", "│ ", ("quote_marker",))
            for run in block.runs:
                widget.insert("end", run.text, ("quote", *run.tags))
            widget.insert("end", "\n")
        else:  # paragraph
            for run in block.runs:
                widget.insert("end", run.text, run.tags)
            widget.insert("end", "\n")

    widget.configure(state="disabled")
