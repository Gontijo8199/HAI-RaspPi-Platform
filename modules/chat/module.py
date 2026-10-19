"""
Módulo "Conversar com a IA": liga a tela (controller.py + Page.qml) à lógica
(session.py) e aos serviços compartilhados (LLM, TTS, câmera, Whisper).

Recursos por entrada no módulo (abertos em enter, liberados em exit):
- microfone (VoiceRecorder, pausado entre gravações);
- a ChatSession (histórico, rascunho e fotos só em memória);
- tarefas assíncronas da tela.
Os serviços compartilhados continuam vivos ao voltar para o menu.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine

from modules.base import Module
from modules.chat.controller import ChatController
from modules.chat.session import ChatSession

logger = logging.getLogger(__name__)


class ChatModule(Module):
    id = "chat"
    title = "Conversar com a IA"
    summary = "Pergunte com texto, voz e fotos"
    uses_speech = True

    def __init__(self, services):
        super().__init__(services)
        self.session: ChatSession | None = None
        self.controller: ChatController | None = None
        self._tasks: set[asyncio.Task] = set()

    def unavailable_reason(self) -> str | None:
        return self.services.llm_problem

    async def enter(self, go_back: Callable[[], None]) -> ChatController:
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
        self.controller = ChatController(
            self.session,
            go_back,
            voice_output_available=services.voice_output_available,
            spawn=self._spawn,
        )
        self.session.listener = self.controller
        await self.session.start()
        return self.controller

    async def exit(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.session is not None:
            await self.session.stop()
        if self.controller is not None:
            self.controller.close()
        self.session, self.controller = None, None

    def _spawn(self, coro: Coroutine) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
