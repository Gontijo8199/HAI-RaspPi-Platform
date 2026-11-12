"""
Estado e ações da tela "Gerar imagem" (Page.qml só lê e chama isto).

A imagem gerada fica só na memória (ui.images) e some na saída do módulo.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Coroutine

from PySide6.QtCore import Property, QObject, Signal, Slot

from api.llm_client import LLMError
from ui import images

_entries = itertools.count(1)


class ImageGenController(QObject):
    changed = Signal()

    def __init__(
        self, title: str, go_back: Callable[[], None], llm, spawn: Callable[[Coroutine], None]
    ):
        super().__init__()
        self._title = title
        self._go_back = go_back
        self._llm = llm
        self._spawn = spawn
        self._prefix = f"gerar{next(_entries)}-"
        self._shots = itertools.count(1)
        self._status = ""
        self._error = False
        self._busy = False
        self._image = ""
        self._closed = False

    # ------------------------------------------------------------------ estado

    def _get_title(self) -> str:
        return self._title

    def _get_status(self) -> str:
        return self._status

    def _get_error(self) -> bool:
        return self._error

    def _get_busy(self) -> bool:
        return self._busy

    def _get_image(self) -> str:
        return self._image

    title = Property(str, _get_title, constant=True)
    status = Property(str, _get_status, notify=changed)
    error = Property(bool, _get_error, notify=changed)
    busy = Property(bool, _get_busy, notify=changed)
    image = Property(str, _get_image, notify=changed)

    # ------------------------------------------------------------------ ações

    @Slot(str)
    def generate(self, prompt: str) -> None:
        if self._closed or self._busy:
            return
        prompt = prompt.strip()
        if not prompt:
            self._show("Descreva a imagem primeiro.", error=True)
            return
        self._busy = True
        self._show("Gerando… isso pode levar alguns segundos.")
        self._spawn(self._generate(prompt))

    @Slot()
    def back(self) -> None:
        if not self._closed:
            self._go_back()

    def close(self) -> None:
        self._closed = True
        images.drop(self._prefix)

    # ------------------------------------------------------------------ interno

    async def _generate(self, prompt: str) -> None:
        try:
            data = await self._llm.generate_image(prompt)
        except LLMError as exc:
            if not self._closed:
                self._show(f"Deu erro: {exc}", error=True)
            return
        finally:
            self._busy = False
        if self._closed:
            return
        images.drop(self._prefix)  # só a última imagem fica na memória
        # Chave nova a cada imagem: o Qt guarda cache por endereço.
        self._image = images.put(f"{self._prefix}{next(self._shots)}", data)
        self._show("Pronto! 🎉")

    def _show(self, status: str, *, error: bool = False) -> None:
        self._status, self._error = status, error
        self.changed.emit()
