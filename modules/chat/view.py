"""
Tela "Conversar com a IA" em Tk, no layout da POC (conversar-llm.html):

    [← Voltar]  Conversar com a IA            [Voz: ligada] [Nova conversa]
    ┌ conversa (balões: aluno à direita, IA à esquerda) ──────────────────┐
    └─────────────────────────────────────────────────────────────────────┘
    ● estado atual / aviso
    ┌ pergunta em montagem: blocos de texto e foto, com ＋ entre eles ─────┐
    └─────────────────────────────────────────────────────────────────────┘
    [● Segurar para falar] [Foto] [Escrever]           [Parar] [Enviar ➤]

A tela não guarda estado de conversa: tudo vem de ChatSession pelos métodos
de ChatListener. Os botões só chamam a sessão.
"""

from __future__ import annotations

import base64
import tkinter as tk
from collections.abc import Callable, Coroutine

from display import tk_markdown
from gui import theme
from gui.theme import Fonts
from gui.widgets import ScrollArea, button, set_style
from modules.chat.session import (
    Activity,
    ChatMessage,
    ChatSession,
    DraftBlock,
    VoiceStatus,
)
from vision.camera import thumbnail_png

_NOTICE_MS = 7000
_PROMPT_HEIGHT = 132
_BUBBLE_MARGIN = 110
_THUMB_DRAFT = 54
_THUMB_MESSAGE = 120

_ACTIVITY_TEXT = {
    Activity.IDLE: "Pronto. Monte sua pergunta falando, escrevendo ou tirando uma foto.",
    Activity.RECORDING: "Gravando… solte o botão para parar.",
    Activity.TRANSCRIBING: "Transcrevendo o áudio…",
    Activity.CAPTURING: "Tirando a foto…",
    Activity.THINKING: "Pergunta enviada. Aguardando a IA…",
    Activity.RESPONDING: "A IA está respondendo…",
    Activity.SPEAKING: "Lendo a resposta em voz alta… (Parar interrompe)",
}
_ACTIVITY_DOT = {
    Activity.IDLE: theme.GREEN,
    Activity.RECORDING: theme.RED,
    Activity.SPEAKING: theme.BLUE,
}
_CANCELLABLE = {
    Activity.RECORDING,
    Activity.TRANSCRIBING,
    Activity.CAPTURING,
    Activity.THINKING,
    Activity.RESPONDING,
    Activity.SPEAKING,
}

_WELCOME = (
    "Olá! Monte sua pergunta falando, escrevendo ou mandando uma foto. "
    "Quando estiver pronta, toque em Enviar."
)


class ChatView:
    """Implementa ChatListener e monta os widgets dentro de `parent`."""

    def __init__(
        self,
        parent: tk.Frame,
        session: ChatSession,
        fonts: Fonts,
        go_back: Callable[[], None],
        voice_output_available: bool,
        spawn: Callable[[Coroutine], None],
    ):
        self._session = session
        self._spawn = spawn
        self._fonts = fonts
        self._root = parent.winfo_toplevel()
        # Miniaturas vivas por (bloco, tamanho) — sem referência o Tk apaga a imagem.
        # Liberadas em "Nova conversa" e na saída do módulo.
        self._images: dict[tuple[int, int], tk.PhotoImage] = {}
        self._message_widgets: dict[int, tuple[tk.Frame, tk.Text]] = {}
        self._draft_texts: dict[int, tk.Text] = {}
        self._notice_job: str | None = None
        self._notice: tuple[str, str] | None = None
        self._destroyed = False

        self.frame = parent
        # Cabeçalho e controles primeiro: se faltar altura (fonte maior, tela menor),
        # o Tk encolhe a área da conversa, nunca os botões.
        self._build_header(go_back, voice_output_available)
        self._build_controls()
        self._build_body()

        self.conversation_cleared()
        self.draft_changed(session.draft, None)
        self.activity_changed(session.activity)
        self.voice_status_changed(session.voice_status, session.voice_reason)

    # ------------------------------------------------------------------ montagem

    def _build_header(self, go_back: Callable[[], None], voice_output: bool) -> None:
        bar = tk.Frame(self.frame, bg=theme.BG)
        bar.pack(fill="x", padx=20, pady=(12, 8))
        self.back_button = button(
            bar, "← Voltar", go_back, kind="secondary", font=self._fonts.button
        )
        self.back_button.pack(side="left")
        tk.Label(
            bar, text="Conversar com a IA", font=self._fonts.title, bg=theme.BG, fg=theme.TEXT
        ).pack(side="left", padx=16)
        self.new_button = button(
            bar, "Nova conversa", self._new_conversation, kind="secondary", font=self._fonts.small
        )
        self.new_button.pack(side="right")
        self.voice_button: tk.Button | None = None
        if voice_output:
            self.voice_button = button(
                bar, "", self._toggle_voice, kind="secondary", font=self._fonts.small
            )
            self.voice_button.pack(side="right", padx=(0, 10))
            self._paint_voice_button()

    def _build_body(self) -> None:
        body = tk.Frame(self.frame, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=20)

        self.conversation = ScrollArea(body, bg=theme.CARD)
        self.conversation.pack(fill="both", expand=True)

        status = tk.Frame(body, bg=theme.BG)
        status.pack(fill="x", pady=(6, 6))
        self._dot = tk.Label(status, text="●", font=self._fonts.small, bg=theme.BG)
        self._dot.pack(side="left")
        self.status_label = tk.Label(
            status, text="", font=self._fonts.small, bg=theme.BG, fg=theme.MUTED, anchor="w"
        )
        self.status_label.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.prompt = ScrollArea(body, bg=theme.CARD, pad=8)
        self.prompt.configure(height=_PROMPT_HEIGHT)
        self.prompt.pack_propagate(False)
        self.prompt.pack(fill="x")

    def _build_controls(self) -> None:
        bar = tk.Frame(self.frame, bg=theme.BG)
        bar.pack(side="bottom", fill="x", padx=20, pady=(8, 12))
        f = self._fonts.button

        self.mic_button = button(bar, "● Segurar para falar", None, kind="success", font=f)
        self.mic_button.pack(side="left")
        self.mic_button.bind("<ButtonPress-1>", self._mic_press)
        self.mic_button.bind("<ButtonRelease-1>", self._mic_release)

        self.photo_button = button(bar, "Foto", self._take_photo, kind="secondary", font=f)
        if self._session.camera_available:
            self.photo_button.pack(side="left", padx=(10, 0))

        self.write_button = button(bar, "Escrever", self._add_text, kind="secondary", font=f)
        self.write_button.pack(side="left", padx=(10, 0))

        self.send_button = button(bar, "Enviar ➤", self._send, kind="primary", font=f)
        self.send_button.pack(side="right")
        self.stop_button = button(bar, "■ Parar", self._session.cancel, kind="danger", font=f)

    # ------------------------------------------------------------------ ações

    def _mic_press(self, _event: tk.Event) -> str:
        if self._session.voice_status is not VoiceStatus.READY:
            self.notice("error", self._session.voice_reason or "Entrada por voz indisponível.")
            return "break"
        if self.mic_button["state"] == "disabled":
            return "break"  # outra atividade em andamento
        self._sync_texts()
        self._session.begin_recording()
        return "break"

    def _mic_release(self, _event: tk.Event) -> str:
        self._session.finish_recording()
        return "break"

    def _take_photo(self) -> None:
        self._sync_texts()
        self._session.take_photo()

    def _add_text(self) -> None:
        self._sync_texts()
        self._session.add_text_block()

    def _insert_text(self, index: int) -> None:
        self._sync_texts()
        self._session.add_text_block(index)

    def _remove(self, block_id: int) -> None:
        self._sync_texts()
        self._session.remove_block(block_id)

    def _send(self) -> None:
        self._sync_texts()
        self._session.send()

    def _new_conversation(self) -> None:
        self._root.focus_set()
        self._spawn(self._session.new_conversation())

    def _toggle_voice(self) -> None:
        self._session.set_voice_output(not self._session.voice_output)
        self._paint_voice_button()

    def _paint_voice_button(self) -> None:
        if self.voice_button is not None:
            on = self._session.voice_output
            self.voice_button.configure(text="Voz: ligada" if on else "Voz: desligada")

    def _sync_texts(self) -> None:
        """Copia o texto dos campos para a sessão (antes de redesenhar ou enviar)."""
        for block_id, widget in self._draft_texts.items():
            try:
                self._session.set_text(block_id, widget.get("1.0", "end-1c"))
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ ChatListener

    def activity_changed(self, activity: Activity) -> None:
        if self._destroyed:
            return
        busy = activity not in (Activity.IDLE, Activity.SPEAKING)
        recording = activity is Activity.RECORDING
        self.mic_button.configure(
            text="● Gravando… solte para parar" if recording else "● Segurar para falar"
        )
        self.photo_button.configure(
            text="Tirando foto…" if activity is Activity.CAPTURING else "Foto"
        )
        set_style(self.photo_button, "secondary", enabled=not busy)
        set_style(self.send_button, "primary", enabled=not busy)
        if activity in _CANCELLABLE and activity is not Activity.RECORDING:
            self.stop_button.pack(side="right", padx=(0, 10), after=self.send_button)
        else:
            self.stop_button.pack_forget()
        self._paint_mic()
        self._paint_status()

    def voice_status_changed(self, status: VoiceStatus, reason: str) -> None:
        if self._destroyed:
            return
        self._paint_mic()

    def draft_changed(self, blocks: list[DraftBlock], focus_id: int | None) -> None:
        if self._destroyed:
            return
        focused = self._focused_block()
        if focus_id is None and focused is not None:
            focus_id, cursor = focused
        else:
            cursor = "end"
        inner = self.prompt.inner
        for child in inner.winfo_children():
            child.destroy()
        self._draft_texts.clear()

        if not blocks:
            hint = tk.Label(
                inner,
                text="Fale, escreva ou tire uma foto para montar sua pergunta.",
                font=self._fonts.small,
                bg=theme.CARD,
                fg=theme.HINT,
            )
            hint.pack(anchor="w", padx=6, pady=6)
            self.prompt.track(hint)
            return

        for index, block in enumerate(blocks):
            self._insert_row(inner, index)
            self._block_row(inner, block)
        self._insert_row(inner, len(blocks))

        if focus_id in self._draft_texts:
            widget = self._draft_texts[focus_id]
            widget.focus_set()
            widget.mark_set("insert", cursor)
            self._root.after_idle(lambda: self._reveal(widget))
        else:
            self.prompt.scroll_to_end()

    def message_added(self, message: ChatMessage) -> None:
        if self._destroyed:
            return
        follow = self.conversation.at_end()
        inner = self.conversation.inner
        if message.role == "user":
            bubble = tk.Frame(inner, bg=theme.USER_BUBBLE, padx=14, pady=10)
            bubble.pack(anchor="e", padx=(_BUBBLE_MARGIN, 0), pady=5)
            self.conversation.track(bubble)
            for block in message.blocks:
                self._message_part(bubble, block)
        else:
            bubble = tk.Frame(inner, bg=theme.AI_BUBBLE, padx=14, pady=8)
            bubble.pack(fill="x", anchor="w", padx=(0, _BUBBLE_MARGIN), pady=5)
            text = self._reply_text(bubble)
            self._message_widgets[message.id] = (bubble, text)
            self._paint_reply(message)
        if follow or message.role == "user":
            self.conversation.scroll_to_end()

    def message_updated(self, message: ChatMessage) -> None:
        if self._destroyed:
            return
        follow = self.conversation.at_end()
        self._paint_reply(message)
        if follow:
            self.conversation.scroll_to_end()

    def conversation_cleared(self) -> None:
        if self._destroyed:
            return
        for child in self.conversation.inner.winfo_children():
            child.destroy()
        self._message_widgets.clear()
        self._images.clear()
        welcome = ChatMessage(id=0, role="ai", text=_WELCOME)
        self.message_added(welcome)
        self.conversation.scroll_to_top()

    def notice(self, kind: str, text: str) -> None:
        if self._destroyed or not text:
            return
        self._notice = (kind, text)
        if self._notice_job is not None:
            self._root.after_cancel(self._notice_job)
        self._notice_job = self._root.after(_NOTICE_MS, self._clear_notice)
        self._paint_status()

    # ------------------------------------------------------------------ desenho

    def _paint_status(self) -> None:
        activity = self._session.activity
        if self._notice is not None and activity in (Activity.IDLE, Activity.SPEAKING):
            kind, text = self._notice
            color = theme.ERROR_FG if kind == "error" else theme.INFO_FG
            self._dot.configure(fg=color)
            self.status_label.configure(text=text, fg=color)
            return
        self._dot.configure(fg=_ACTIVITY_DOT.get(activity, theme.BLUE))
        self.status_label.configure(text=_ACTIVITY_TEXT[activity], fg=theme.MUTED)

    def _clear_notice(self) -> None:
        self._notice_job = None
        self._notice = None
        if not self._destroyed:
            self._paint_status()

    def _paint_mic(self) -> None:
        status = self._session.voice_status
        activity = self._session.activity
        if status is VoiceStatus.LOADING:
            self.mic_button.configure(text="Preparando a voz…")
            set_style(self.mic_button, "success", enabled=False)
        elif status is VoiceStatus.UNAVAILABLE:
            self.mic_button.configure(text="Voz indisponível")
            set_style(self.mic_button, "success", enabled=False)
        else:
            busy = activity not in (Activity.IDLE, Activity.SPEAKING, Activity.RECORDING)
            kind = "danger" if activity is Activity.RECORDING else "success"
            set_style(self.mic_button, kind, enabled=not busy)

    def _insert_row(self, parent: tk.Frame, index: int) -> None:
        row = tk.Frame(parent, bg=theme.CARD)
        row.pack(fill="x")
        b = button(
            row,
            "＋",
            lambda: self._insert_text(index),
            kind="insert",
            font=self._fonts.tiny,
            padx=26,
            pady=0,
        )
        b.pack()
        self.prompt.track(row)

    def _block_row(self, parent: tk.Frame, block: DraftBlock) -> None:
        row = tk.Frame(parent, bg=theme.BLOCK_BG, padx=10, pady=6)
        row.pack(fill="x", pady=1)
        self.prompt.track(row)
        remove = button(
            row,
            "✕",
            lambda: self._remove(block.id),
            kind="remove",
            font=self._fonts.small,
            padx=16,
            pady=6,
        )
        remove.pack(side="right", padx=(10, 0))

        if block.kind == "photo":
            image = self._thumbnail(block, _THUMB_DRAFT)
            if image is not None:
                pic = tk.Label(row, image=image, bg=theme.BLOCK_BG)
                pic.pack(side="left", padx=(0, 10))
                self.prompt.track(pic)
            label = tk.Label(
                row, text=block.label, font=self._fonts.body, bg=theme.BLOCK_BG, fg=theme.TEXT
            )
            label.pack(side="left")
            self.prompt.track(label)
            return

        if block.pending is not None:
            label = tk.Label(
                row,
                text=block.pending,
                font=self._fonts.body,
                bg=theme.BLOCK_BG,
                fg=theme.MUTED,
                anchor="w",
            )
            label.pack(side="left", fill="x", expand=True)
            self.prompt.track(label)
            return

        text = tk.Text(
            row,
            height=1,
            width=1,
            wrap="word",
            font=self._fonts.body,
            bg=theme.BLOCK_BG,
            fg=theme.TEXT,
            insertbackground=theme.TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=theme.BLOCK_BG,
            highlightcolor=theme.BLUE,
            undo=True,
        )
        text.insert("1.0", block.text)
        text.pack(side="left", fill="x", expand=True)
        text.bind("<KeyRelease>", lambda _e: self._on_edit(block.id, text))
        text.bind("<FocusOut>", lambda _e: self._on_edit(block.id, text))
        text.bind("<Return>", lambda _e: (self._send(), "break")[1])
        text.bind("<Shift-Return>", lambda _e: None)
        self._draft_texts[block.id] = text
        text.bind("<Configure>", lambda _e: self._fit_text(text, max_lines=4))

    def _on_edit(self, block_id: int, widget: tk.Text) -> None:
        try:
            self._session.set_text(block_id, widget.get("1.0", "end-1c"))
        except tk.TclError:
            return
        self._fit_text(widget, max_lines=4)

    def _message_part(self, bubble: tk.Frame, block: DraftBlock) -> None:
        if block.kind == "photo":
            image = self._thumbnail(block, _THUMB_MESSAGE)
            if image is not None:
                pic = tk.Label(bubble, image=image, bg=theme.USER_BUBBLE)
                pic.pack(anchor="e", pady=2)
                self.conversation.track(pic)
            caption = tk.Label(
                bubble,
                text=f"[{block.label}]",
                font=self._fonts.small,
                bg=theme.USER_BUBBLE,
                fg=theme.MUTED,
            )
            caption.pack(anchor="e")
            self.conversation.track(caption)
            return
        label = tk.Label(
            bubble,
            text=block.text.strip(),
            font=self._fonts.body,
            bg=theme.USER_BUBBLE,
            fg=theme.TEXT,
            wraplength=560,
            justify="left",
        )
        label.pack(anchor="e", pady=2)
        self.conversation.track(label)

    def _reply_text(self, bubble: tk.Frame) -> tk.Text:
        text = tk.Text(
            bubble,
            height=1,
            width=1,
            wrap="word",
            font=self._fonts.body,
            bg=theme.AI_BUBBLE,
            fg=theme.TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            cursor="arrow",
            takefocus=0,
            state="disabled",
        )
        tk_markdown.configure_tags(text, self._fonts.body, self._fonts.mono, tk_markdown.LIGHT)
        text.tag_configure("muted", foreground=theme.MUTED, font=self._fonts.small)
        text.tag_configure("error", foreground=theme.ERROR_FG)
        text.pack(fill="x")
        self.conversation.track(text)
        self.conversation.track(bubble)
        text.bind("<Configure>", lambda _e: self._fit_text(text))
        return text

    def _paint_reply(self, message: ChatMessage) -> None:
        widgets = self._message_widgets.get(message.id)
        if widgets is None:
            return
        _bubble, text = widgets
        # Markdown renderizado a cada atualização: a resposta já aparece formatada
        # enquanto chega (o texto é curto, ~120 palavras).
        tk_markdown.render(text, message.text)
        if message.status not in ("done", "streaming"):
            text.configure(state="normal")
            if message.status == "thinking":
                text.insert("end", "Pensando…", ("muted",))
            else:
                # render() já termina o texto parcial com quebra de linha.
                if message.status == "cancelled":
                    text.insert("end", "(resposta interrompida)", ("muted",))
                elif message.status == "error":
                    text.insert("end", f"Deu erro: {message.error}", ("error",))
                    text.insert(
                        "end",
                        "\nSua pergunta voltou para edição: toque em Enviar para tentar de novo.",
                        ("muted",),
                    )
            text.configure(state="disabled")
        self._fit_text(text)

    def _thumbnail(self, block: DraftBlock, size: int) -> tk.PhotoImage | None:
        key = (block.id, size)
        if key in self._images:
            return self._images[key]
        png = thumbnail_png(block.image, size) if block.image is not None else None
        if png is None:
            return None
        image = tk.PhotoImage(master=self._root, data=base64.b64encode(png).decode("ascii"))
        self._images[key] = image
        return image

    @staticmethod
    def _fit_text(widget: tk.Text, max_lines: int | None = None) -> None:
        """Ajusta a altura (em linhas) do Text ao conteúdo já quebrado."""
        try:
            if widget.winfo_width() <= 1:
                return  # ainda sem largura real: o <Configure> chama de novo
            # A quebra de linha final (do Markdown ou do próprio Tk) não conta.
            last = "end-2c" if widget.get("end-2c", "end-1c") == "\n" else "end-1c"
            count = widget.count("1.0", last, "displaylines")
        except tk.TclError:
            return
        if isinstance(count, tuple):
            count = count[0]
        lines = int(count or 0) + 1
        if max_lines is not None:
            lines = min(lines, max_lines)
        if int(widget.cget("height")) != lines:
            widget.configure(height=lines)

    def _focused_block(self) -> tuple[int, str] | None:
        focus = self._root.focus_get()
        for block_id, widget in self._draft_texts.items():
            if widget is focus:
                return block_id, widget.index("insert")
        return None

    def _reveal(self, widget: tk.Misc) -> None:
        if self._destroyed:
            return
        try:
            if widget.winfo_y() + widget.winfo_height() > self.prompt.winfo_height():
                self.prompt.scroll_to_end()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        """Cancela timers e solta as imagens (os widgets morrem com o frame do app)."""
        self._destroyed = True
        if self._notice_job is not None:
            try:
                self._root.after_cancel(self._notice_job)
            except tk.TclError:
                pass
            self._notice_job = None
        self._images.clear()
        self._draft_texts.clear()
        self._message_widgets.clear()
