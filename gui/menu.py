"""
Menu principal: grade de cartões (POC index.html), um por módulo registrado.

Só aparecem os módulos de modules.build_modules(); não há cartões de
atividades futuras. Um módulo indisponível (ex.: sem chave da API) continua
visível, com o motivo escrito no cartão, e o toque mostra a explicação.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from gui import theme
from gui.theme import Fonts
from modules.base import Module

_COLUMNS = 4
_CARD_SIZE = (220, 190)
_ICON_SIZE = 84


class MenuScreen:
    def __init__(
        self,
        parent: tk.Misc,
        modules: list[Module],
        fonts: Fonts,
        on_open: Callable[[Module], None],
    ):
        self._fonts = fonts
        self._on_open = on_open
        self.frame = tk.Frame(parent, bg=theme.BG)
        self.cards: dict[str, tk.Frame] = {}

        header = tk.Frame(self.frame, bg=theme.BG)
        header.pack(fill="x", padx=28, pady=(26, 6))
        tk.Label(header, text="IA na Educação", font=fonts.title, bg=theme.BG, fg=theme.TEXT).pack(
            anchor="w"
        )
        tk.Label(
            header,
            text="Toque em uma atividade para começar.",
            font=fonts.small,
            bg=theme.BG,
            fg=theme.MUTED,
        ).pack(anchor="w")

        grid = tk.Frame(self.frame, bg=theme.BG)
        grid.pack(fill="x", padx=20, pady=12)
        for index, module in enumerate(modules):
            card = self._card(grid, module)
            card.grid(row=index // _COLUMNS, column=index % _COLUMNS, padx=10, pady=10, sticky="n")
            self.cards[module.id] = card

        self._message = tk.Label(
            self.frame,
            text="",
            font=fonts.small,
            wraplength=900,
            justify="left",
            anchor="w",
            padx=16,
            pady=10,
        )

    def show(self) -> None:
        self.frame.pack(fill="both", expand=True)

    def hide(self) -> None:
        self.frame.pack_forget()

    def show_message(self, text: str, kind: str = "error") -> None:
        """Aviso no rodapé do menu (problemas de configuração, falha ao abrir)."""
        if not text:
            self._message.pack_forget()
            return
        bg, fg = (
            (theme.ERROR_BG, theme.ERROR_FG) if kind == "error" else (theme.INFO_BG, theme.INFO_FG)
        )
        self._message.configure(text=text, bg=bg, fg=fg)
        self._message.pack(side="bottom", fill="x", padx=28, pady=(0, 24))

    @property
    def message(self) -> str:
        return self._message.cget("text") if self._message.winfo_ismapped() else ""

    def _card(self, parent: tk.Misc, module: Module) -> tk.Frame:
        width, height = _CARD_SIZE
        reason = module.unavailable_reason()
        card = tk.Frame(
            parent,
            bg=theme.CARD,
            width=width,
            height=height,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            cursor="hand2",
        )
        card.pack_propagate(False)

        icon = tk.Canvas(
            card, width=_ICON_SIZE, height=_ICON_SIZE, bg=theme.CARD, highlightthickness=0
        )
        icon.pack(pady=(20, 6))
        module.draw_icon(icon, _ICON_SIZE)

        title = tk.Label(
            card,
            text=module.title,
            font=self._fonts.body_bold,
            bg=theme.CARD,
            fg=theme.TEXT if reason is None else theme.HINT,
            wraplength=width - 24,
        )
        title.pack()
        widgets: list[tk.Misc] = [card, icon, title]
        if reason is not None:
            note = tk.Label(
                card,
                text="Indisponível — toque para ver",
                font=self._fonts.tiny,
                bg=theme.CARD,
                fg=theme.ERROR_FG,
            )
            note.pack(pady=(4, 0))
            widgets.append(note)

        def press(_event: tk.Event) -> None:
            for w in widgets:
                w.configure(bg=theme.INSERT_BG)

        def release(event: tk.Event) -> None:
            for w in widgets:
                w.configure(bg=theme.CARD)
            # Só abre se o dedo foi solto em cima do cartão (arrastar para fora cancela).
            x, y = event.x_root - card.winfo_rootx(), event.y_root - card.winfo_rooty()
            if 0 <= x < card.winfo_width() and 0 <= y < card.winfo_height():
                self._on_open(module)

        for w in widgets:
            w.bind("<ButtonPress-1>", press)
            w.bind("<ButtonRelease-1>", release)
        return card
