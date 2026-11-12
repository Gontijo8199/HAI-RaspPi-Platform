"""
Módulo "Treinar reconhecedor": o aluno cria classes, tira fotos de cada uma,
treina um KNN sobre os vetores da MobileNetV2 e testa com fotos novas.

Recursos por entrada: o controller (classes, fotos e vetores só em memória),
a câmera aberta da prévia ao vivo e as tarefas assíncronas da tela, liberados
em exit() (cancelar a prévia fecha a câmera). O extrator (embedder.py)
carrega na primeira foto, em thread, e fica no módulo entre entradas (é
caro carregar e barato manter); close() o solta.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

from modules.base import Module
from modules.treinar_imagem.controller import TrainerController
from modules.treinar_imagem.embedder import Embedder


class TrainerModule(Module):
    id = "treinar_imagem"
    title = "Treinar reconhecedor"
    summary = "Ensine o computador a reconhecer imagens"

    def __init__(self, services):
        super().__init__(services)
        self.controller: TrainerController | None = None
        self.embedder = None
        self._load_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    def unavailable_reason(self) -> str | None:
        if self.services.camera is None:
            return "Câmera desativada: ligue [camera] enabled em config/settings.toml."
        return None

    async def enter(self, go_back: Callable[[], None]) -> TrainerController:
        self.controller = TrainerController(
            self.title, go_back, self.services.camera, self._get_embedder, self._spawn
        )
        self.controller.start()
        return self.controller

    async def exit(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.controller is not None:
            self.controller.close()
        self.controller = None

    async def close(self) -> None:
        self.embedder = None

    async def _get_embedder(self):
        async with self._load_lock:  # dois toques seguidos não carregam o modelo duas vezes
            if self.embedder is None:
                self.embedder = await asyncio.to_thread(Embedder)
        return self.embedder

    def _spawn(self, coro: Coroutine) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
