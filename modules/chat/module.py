"""
Módulo "Conversar com a IA": liga a tela (view.py) à lógica (session.py) e aos
serviços compartilhados (LLM, TTS, câmera, Whisper).

Recursos por entrada no módulo (abertos em enter, liberados em exit):
- microfone (VoiceRecorder, pausado entre gravações);
- a ChatSession (histórico, rascunho e fotos só em memória);
- tarefas assíncronas da tela.
Os serviços compartilhados continuam vivos ao voltar para o menu.
"""

from __future__ import annotations

import asyncio
import logging
import tkinter as tk
from collections.abc import Callable, Coroutine

from gui import theme
from modules.base import Module
from modules.chat.session import ChatSession
from modules.chat.view import ChatView

logger = logging.getLogger(__name__)


class ChatModule(Module):
    id = "chat"
    title = "Conversar com a IA"

    def __init__(self, services):
        super().__init__(services)
        self.session: ChatSession | None = None
        self.view: ChatView | None = None
        self._tasks: set[asyncio.Task] = set()

    def unavailable_reason(self) -> str | None:
        return self.services.llm_problem

    def draw_icon(self, canvas: tk.Canvas, size: int) -> None:
        # Balão de conversa com três pontinhos (sem emoji: ver gui/theme.py).
        m = size * 0.12
        canvas.create_rectangle(
            m, m, size - m, size * 0.72, fill=theme.BLUE, outline=theme.BLUE, width=0
        )
        canvas.create_polygon(
            size * 0.28, size * 0.70, size * 0.28, size * 0.90, size * 0.50, size * 0.70,
            fill=theme.BLUE, outline=theme.BLUE,
        )  # fmt: skip
        r = size * 0.055
        for cx in (0.32, 0.5, 0.68):
            x, y = size * cx, size * 0.42
            canvas.create_oval(x - r, y - r, x + r, y + r, fill="#ffffff", outline="#ffffff")

    async def enter(self, parent: tk.Frame, go_back: Callable[[], None]) -> None:
        services = self.services
        recorder = None
        try:
            recorder = services.make_recorder()
        except Exception as exc:  # PyAudio ausente/quebrado: segue sem voz
            logger.warning("Entrada por voz indisponível: %s", exc)

        self.session = ChatSession(
            llm=services.llm,
            tts=services.tts,
            camera=services.camera,
            recorder=recorder,
            get_asr=services.get_asr if recorder is not None else None,
        )
        self.view = ChatView(
            parent,
            self.session,
            theme.fonts_for(parent),
            go_back,
            voice_output_available=services.voice_output_available,
            spawn=self._spawn,
        )
        self.session.listener = self.view
        await self.session.start()

    async def exit(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.session is not None:
            await self.session.stop()
        if self.view is not None:
            self.view.destroy()
        self.session, self.view = None, None

    def _spawn(self, coro: Coroutine) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
