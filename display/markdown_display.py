"""
Design (mesmo padrão de tts/speaker.py):
- Thread dedicada roda o mainloop do Tkinter; nada de UI acontece fora dela.
- show_response()/show_flashcard()/clear() são fire-and-forget: apenas
  colocam uma mensagem numa Queue (thread-safe) e retornam imediatamente.
- A thread de display consome a fila via root.after(...), sem bloquear o
  event loop do Tkinter.
- Se não houver Tk instalado ou não houver $DISPLAY (ex.: SSH sem X forward,
  CI, pytest), o driver cai automaticamente em modo headless: os métodos
  continuam funcionando (não lançam exceção), só não desenham nada. Isso
  mantém o resto do pipeline 100% funcional e testável sem hardware.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Any

from display.markdown_parser import parse_markdown

logger = logging.getLogger(__name__)

_STOP = object()


class MarkdownDisplay:
    """Janela X11 (Tkinter) que exibe respostas / flash-cards em Markdown.

    Parâmetros
    ----------
    fullscreen : bool
        Abre em tela cheia (recomendado para o HDMI do Pi rodando em kiosk).
    width, height : int
        Dimensões da janela quando não está em fullscreen.
    font_family : str
        Fonte usada no corpo do texto.
    font_size : int
        Tamanho de fonte base (headings escalam a partir dele).
    flashcard_width : int
        Largura em pixels do painel lateral do flash-card.
    bg / fg : str
        Cores de fundo/texto do painel principal.
    flashcard_bg / flashcard_fg : str
        Cores de fundo/texto do painel do flash-card.
    display_env : str
        Valor padrão para a variável de ambiente DISPLAY caso ela não esteja
        definida (útil para autostart via systemd/cron no Pi: ":0").
    headless : bool
        Força modo headless (nunca toca em Tk/Tcl), sem tentar detectar o ambiente.
        Usado pela suíte de testes: criar/destruir janelas Tk de verdade repetidamente,
        em threads diferentes, dentro do mesmo processo, é instável no Tcl.
    """

    def __init__(
        self,
        fullscreen: bool = True,
        width: int = 1024,
        height: int = 600,
        font_family: str = "DejaVu Sans Mono",
        font_size: int = 20,
        flashcard_width: int = 340,
        bg: str = "#1e1e1e",
        fg: str = "#e6e6e6",
        flashcard_bg: str = "#25314d",
        flashcard_fg: str = "#f2f2f2",
        display_env: str = ":0",
        headless: bool = False,
    ):
        self._fullscreen = fullscreen
        self._width = width
        self._height = height
        self._font_family = font_family
        self._font_size = font_size
        self._flashcard_width = flashcard_width
        self._bg = bg
        self._fg = fg
        self._flashcard_bg = flashcard_bg
        self._flashcard_fg = flashcard_fg
        self._display_env = display_env
        self._force_headless = headless

        self._queue: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._available = False

        self._root: Any = None
        self._response_text: Any = None
        self._flashcard_text: Any = None

        self._thread = threading.Thread(target=self._run, daemon=True, name="display-worker")
        self._thread.start()
        # Aguarda a thread inicializar (ou falhar) antes de seguir, para que self.available já reflita a realidade assim que o construtor retornar.
        self._ready.wait(timeout=5.0)

    @property
    def available(self) -> bool:
        return self._available

    def show_response(self, markdown_text: str) -> None:
        self._queue.put(("response", markdown_text))

    def show_flashcard(self, markdown_text: str) -> None:
        self._queue.put(("flashcard", markdown_text))

    def clear(self) -> None:
        self._queue.put(("clear", None))

    def shutdown(self) -> None:
        self._queue.put(("stop", None))
        self._thread.join(timeout=3.0)
        logger.info("MarkdownDisplay encerrado.")

    def _run(self) -> None:
        if self._force_headless:
            self._available = False
            self._ready.set()
            self._run_headless_loop()
            return
        try:
            self._init_window()
            self._available = True
            logger.info("MarkdownDisplay: janela X11 iniciada.")
        except Exception as exc:
            logger.warning(
                "MarkdownDisplay: não foi possível abrir janela X11 (%s). "
                "Rodando em modo headless, o pipeline continua funcionando "
                "normalmente, apenas sem exibição gráfica.",
                exc,
            )
            self._available = False
        finally:
            self._ready.set()

        if not self._available:
            self._run_headless_loop()
            return

        self._poll_queue()
        try:
            self._root.mainloop()
        except Exception as exc:
            logger.warning("MarkdownDisplay: mainloop encerrado com erro: %s", exc)
        finally:
            try:
                self._root.destroy()
            except Exception:
                pass

    def _run_headless_loop(self) -> None:
        # Sem janela: apenas drena a fila até receber STOP, para que shutdown() sempre retorne de forma limpa.
        while True:
            item = self._queue.get()
            if item[0] == "stop":
                break

    def _init_window(self) -> None:
        # Import tardio: em ambientes sem Tk (ou sem servidor X) isso lança ImportError / TclError, capturado em _run().
        import tkinter as tk
        from tkinter import font as tkfont

        if not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = self._display_env

        self._tk = tk
        root = tk.Tk()
        root.title("HAI")
        root.configure(bg=self._bg)

        if self._fullscreen:
            root.attributes("-fullscreen", True)
        else:
            root.geometry(f"{self._width}x{self._height}")
        # Esc sempre sai do fullscreen
        root.bind("<Escape>", lambda _e: root.attributes("-fullscreen", False))

        body_font = tkfont.Font(family=self._font_family, size=self._font_size)
        mono_font = tkfont.Font(family=self._font_family, size=self._font_size - 2)
        card_font = tkfont.Font(family=self._font_family, size=self._font_size - 4)

        container = tk.Frame(root, bg=self._bg)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=0)
        container.rowconfigure(0, weight=1)

        response_text = tk.Text(
            container,
            bg=self._bg,
            fg=self._fg,
            insertbackground=self._fg,
            wrap="word",
            padx=24,
            pady=24,
            font=body_font,
            borderwidth=0,
            highlightthickness=0,
            state="disabled",
        )
        response_text.grid(row=0, column=0, sticky="nsew")

        card_frame = tk.Frame(container, bg=self._flashcard_bg, width=self._flashcard_width)
        card_frame.grid(row=0, column=1, sticky="nsew")
        card_frame.grid_propagate(False)

        card_title = tk.Label(
            card_frame,
            text="Resumo do tópico",
            bg=self._flashcard_bg,
            fg=self._flashcard_fg,
            font=tkfont.Font(family=self._font_family, size=self._font_size - 4, weight="bold"),
            anchor="w",
            padx=16,
            pady=12,
        )
        card_title.pack(fill="x")

        flashcard_text = tk.Text(
            card_frame,
            bg=self._flashcard_bg,
            fg=self._flashcard_fg,
            insertbackground=self._flashcard_fg,
            wrap="word",
            padx=16,
            pady=8,
            font=card_font,
            borderwidth=0,
            highlightthickness=0,
            state="disabled",
        )
        flashcard_text.pack(fill="both", expand=True)

        self._configure_tags(response_text, body_font, mono_font)
        self._configure_tags(flashcard_text, card_font, mono_font)

        self._root = root
        self._response_text = response_text
        self._flashcard_text = flashcard_text

    def _configure_tags(self, widget: Any, body_font: Any, mono_font: Any) -> None:
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
            "code", font=(mono_font.cget("family"), mono_font.cget("size")), background="#333333"
        )
        widget.tag_configure(
            "code_block",
            font=(mono_font.cget("family"), mono_font.cget("size")),
            background="#111111",
            lmargin1=16,
            lmargin2=16,
            spacing1=4,
            spacing3=4,
        )
        widget.tag_configure("quote", foreground="#9fb3c8", font=(family, base_size, "italic"))
        widget.tag_configure("quote_marker", foreground="#5a7a9a")
        widget.tag_configure("bullet_marker", foreground="#7fb0ff")
        widget.tag_configure("hr", foreground="#555555")

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "stop":
                    self._root.quit()
                    return
                elif kind == "response":
                    self._render(self._response_text, payload)
                elif kind == "flashcard":
                    self._render(self._flashcard_text, payload)
                elif kind == "clear":
                    self._render(self._response_text, "")
                    self._render(self._flashcard_text, "")
        except queue.Empty:
            pass
        self._root.after(100, self._poll_queue)

    # Markdown handler
    def _render(self, widget: Any, markdown_text: str) -> None:
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
