"""
Módulo "Gerar imagem": o aluno descreve uma cena e a IA (Gemini, modelo
[api] image_model) desenha. Usa o cliente LLM compartilhado e a mesma chave
do chat.

Recursos por entrada: o controller (imagem só em memória) e a tarefa da
geração, cancelada em exit() (o cliente assíncrono cancela a requisição).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

from modules.base import Module
from modules.gerar_imagem.controller import ImageGenController


class ImageGenModule(Module):
    id = "gerar_imagem"
    title = "Gerar imagem"
    summary = "Descreva e a IA desenha"

    def __init__(self, services):
        super().__init__(services)
        self.controller: ImageGenController | None = None
        self._tasks: set[asyncio.Task] = set()

    def unavailable_reason(self) -> str | None:
        return self.services.llm_problem

    async def enter(self, go_back: Callable[[], None]) -> ImageGenController:
        self.controller = ImageGenController(self.title, go_back, self.services.llm, self._spawn)
        return self.controller

    async def exit(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.controller is not None:
            self.controller.close()
        self.controller = None

    def _spawn(self, coro: Coroutine) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
