"""
Widgets de toque compartilhados pelas telas (menu e módulos).

- button(): botão grande e plano no estilo da POC.
- ScrollArea: área rolável por ARRASTAR o dedo (e pela roda do mouse), sem
  barra de rolagem fina — feita para tela de toque.

Nenhum widget aqui usa bind_all: todos os binds ficam presos aos próprios
widgets e somem quando eles são destruídos (sem listeners acumulados).
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from gui import theme

_STYLES = {
    "primary": (theme.BLUE, "#ffffff", theme.BLUE_DARK),
    "success": (theme.GREEN, "#ffffff", theme.GREEN_DARK),
    "danger": (theme.RED, "#ffffff", theme.RED_DARK),
    "secondary": (theme.CARD, theme.TEXT, theme.INSERT_BG),
    "remove": (theme.REMOVE_BG, theme.REMOVE_FG, "#fecaca"),
    "insert": (theme.INSERT_BG, theme.MUTED, "#cbd5e1"),
}

# Altura mínima de um alvo de toque (px). O padding vertical é calculado pela
# altura real da fonte, então vale para qualquer fonte/DPI instalado no Pi.
TOUCH_MIN_PX = 48


def button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None] | None = None,
    *,
    kind: str = "primary",
    font=None,
    padx: int = 18,
    pady: int | None = None,
) -> tk.Button:
    """Botão plano. Sem `pady`, ganha a altura mínima de toque (TOUCH_MIN_PX)."""
    bg, fg, active = _STYLES[kind]
    if pady is None:
        linespace = font.metrics("linespace") if font is not None else 16
        pady = max(4, (TOUCH_MIN_PX - linespace + 1) // 2)
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=font,
        bg=bg,
        fg=fg,
        activebackground=active,
        activeforeground=fg,
        disabledforeground=theme.HINT if kind == "secondary" else "#e2e8f0",
        relief="flat",
        borderwidth=0,
        highlightthickness=1 if kind == "secondary" else 0,
        highlightbackground=theme.BORDER,
        padx=padx,
        pady=pady,
        cursor="hand2",
        takefocus=0,
    )


def set_style(widget: tk.Button, kind: str, enabled: bool = True) -> None:
    """Aplica o estilo e o estado; desabilitado fica cinza, sem parecer clicável."""
    if enabled:
        bg, fg, active = _STYLES[kind]
        widget.configure(state="normal", bg=bg, fg=fg, activebackground=active, activeforeground=fg)
    else:
        widget.configure(
            state="disabled",
            bg=theme.INSERT_BG,
            activebackground=theme.INSERT_BG,
            disabledforeground=theme.HINT,
        )


class ScrollArea(tk.Frame):
    """Frame rolável. Coloque o conteúdo em `.inner` e chame `.track(widget)`
    nos filhos que devem rolar ao serem arrastados."""

    _DRAG_THRESHOLD = 6  # px: abaixo disso é toque, não arrasto

    def __init__(self, parent: tk.Misc, bg: str = theme.CARD, pad: int = 12):
        super().__init__(parent, bg=bg)
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, borderwidth=0)
        self._canvas.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.inner = tk.Frame(self._canvas, bg=bg)
        self._window = self._canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self._press_y: int | None = None
        self._dragging = False

        self.inner.bind("<Configure>", self._update_region)
        self._canvas.bind("<Configure>", self._fit_width)
        self.track(self._canvas)
        self.track(self.inner)

    def track(self, widget: tk.Misc) -> None:
        """Arrastar este widget rola a área (use em rótulos, imagens, frames)."""
        widget.bind("<ButtonPress-1>", self._on_press, add="+")
        widget.bind("<B1-Motion>", self._on_drag, add="+")
        widget.bind("<ButtonRelease-1>", self._on_release, add="+")
        widget.bind("<Button-4>", lambda _e: self._wheel(-1), add="+")
        widget.bind("<Button-5>", lambda _e: self._wheel(1), add="+")
        widget.bind("<MouseWheel>", lambda e: self._wheel(-1 if e.delta > 0 else 1), add="+")

    def scroll_to_end(self) -> None:
        self.update_idletasks()
        self._update_region()
        self._canvas.yview_moveto(1.0)

    def scroll_to_top(self) -> None:
        self._canvas.yview_moveto(0.0)

    def at_end(self) -> bool:
        return self._canvas.yview()[1] >= 0.999

    def _fit_width(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._window, width=event.width)
        self._update_region()

    def _update_region(self, _event: tk.Event | None = None) -> None:
        height = max(self.inner.winfo_reqheight(), self._canvas.winfo_height())
        self._canvas.configure(scrollregion=(0, 0, self._canvas.winfo_width(), height))

    def _on_press(self, event: tk.Event) -> None:
        self._press_y = event.y_root
        self._dragging = False
        self._canvas.scan_mark(0, event.y_root)

    def _on_drag(self, event: tk.Event) -> None:
        if self._press_y is None:
            return
        if not self._dragging and abs(event.y_root - self._press_y) < self._DRAG_THRESHOLD:
            return
        self._dragging = True
        self._canvas.scan_dragto(0, event.y_root, gain=1)

    def _on_release(self, _event: tk.Event) -> None:
        self._press_y = None
        self._dragging = False

    def _wheel(self, direction: int) -> None:
        self._canvas.yview_scroll(direction * 3, "units")
