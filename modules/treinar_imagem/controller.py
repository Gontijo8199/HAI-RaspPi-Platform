"""
Estado e ações da tela "Treinar reconhecedor" (Page.qml só lê e chama isto).

As classes ficam em `classes` (uma linha por classe: nome, fotos, confiança da
última previsão). O índice da linha é o rótulo no Classifier: classes não são
apagadas, então ele não muda. Fotos e vetores ficam só na memória.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable, Coroutine

from PySide6.QtCore import Property, QObject, Signal, Slot

from modules.treinar_imagem.embedder import EmbedderError
from modules.treinar_imagem.logic import Classifier, training_problem
from ui import images
from ui.models import ListModel
from vision.camera import CameraError

_entries = itertools.count(1)
PREVIEW_INTERVAL_S = 0.1  # ≈10 quadros/s de prévia: leve no Pi


class TrainerController(QObject):
    changed = Signal()

    def __init__(
        self,
        title: str,
        go_back: Callable[[], None],
        camera,
        get_embedder: Callable[[], Awaitable],
        spawn: Callable[[Coroutine], None],
    ):
        super().__init__()
        self._title = title
        self._go_back = go_back
        self._camera = camera
        self._get_embedder = get_embedder
        self._spawn = spawn
        self._prefix = f"treinar{next(_entries)}-"
        self._shots = itertools.count(1)
        self._classifier = Classifier()
        self._classes = ListModel(["name", "photos", "confidence", "winner"], self)
        self._status = "Tire fotos de cada classe com o botão +, depois toque em Treinar."
        self._error = False
        self._busy = False
        self._trained = False
        self._photo = ""
        self._photo_key = ""
        self._frame = None  # último quadro da prévia ao vivo (None = sem prévia)
        self._closed = False
        self.newClass()
        self.newClass()

    # ------------------------------------------------------------------ estado

    def _get_title(self) -> str:
        return self._title

    def _get_classes(self) -> ListModel:
        return self._classes

    def _get_status(self) -> str:
        return self._status

    def _get_error(self) -> bool:
        return self._error

    def _get_busy(self) -> bool:
        return self._busy

    def _get_trained(self) -> bool:
        return self._trained

    def _get_photo(self) -> str:
        return self._photo

    def _get_live(self) -> bool:
        return self._frame is not None

    title = Property(str, _get_title, constant=True)
    classes = Property(QObject, _get_classes, constant=True)
    status = Property(str, _get_status, notify=changed)
    error = Property(bool, _get_error, notify=changed)
    busy = Property(bool, _get_busy, notify=changed)
    trained = Property(bool, _get_trained, notify=changed)
    photo = Property(str, _get_photo, notify=changed)
    live = Property(bool, _get_live, notify=changed)

    # ------------------------------------------------------------------ ações

    @Slot()
    def newClass(self) -> None:  # noqa: N802 (nome visto pela QML)
        if self._closed:
            return
        n = self._classes.rowCount() + 1
        self._classes.append({"name": f"Classe {n}", "photos": 0, "confidence": 0.0})

    @Slot(int, str)
    def rename(self, row: int, name: str) -> None:
        if not self._closed and name.strip() and 0 <= row < self._classes.rowCount():
            self._classes.update(row, name=name.strip())

    @Slot(int)
    def addPhoto(self, row: int) -> None:  # noqa: N802
        if not self._closed and not self._busy and 0 <= row < self._classes.rowCount():
            self._start(self._add_photo(row))

    @Slot()
    def train(self) -> None:
        if self._closed or self._busy:
            return
        problem = training_problem([r["photos"] for r in self._classes.rows])
        if problem:
            self._show(problem, error=True)
            return
        self._trained = True
        self._show("Modelo treinado! Mostre algo para a câmera e toque em Testar. ✅")

    @Slot()
    def test(self) -> None:
        if self._closed or self._busy:
            return
        if not self._trained:
            self._show("Treine o modelo primeiro para ver a previsão.", error=True)
            return
        self._start(self._test())

    @Slot()
    def back(self) -> None:
        if not self._closed:
            self._go_back()

    def start(self) -> None:
        """Liga a prévia ao vivo (o módulo chama ao entrar)."""
        self._spawn(self._preview())

    def close(self) -> None:
        self._closed = True
        self._frame = None
        images.drop(self._prefix)

    # ------------------------------------------------------------------ interno

    def _start(self, coro: Coroutine) -> None:
        # busy já no toque: um segundo toque antes de a tarefa começar é ignorado.
        self._busy = True
        self._show("Tirando foto…")
        self._spawn(self._run(coro))

    async def _run(self, coro: Coroutine) -> None:
        try:
            await coro
        except (CameraError, EmbedderError) as exc:
            if not self._closed:
                self._show(str(exc), error=True)
        finally:
            self._busy = False
            if not self._closed:
                self.changed.emit()

    async def _preview(self) -> None:
        live = self._camera.live()
        try:
            await live.open()
            loop = asyncio.get_running_loop()
            while not self._closed:
                started = loop.time()
                frame = await live.frame()  # espera o próximo quadro da câmera
                if self._closed:
                    break
                self._frame = frame
                self._show_photo(frame.data)
                await asyncio.sleep(max(0.0, PREVIEW_INTERVAL_S - (loop.time() - started)))
        except CameraError as exc:
            self._frame = None
            if not self._closed:
                self._show(f"{exc} Sem prévia: o + tira uma foto a cada toque.", error=True)
        finally:
            await live.close()

    def _show_photo(self, data: bytes) -> None:
        old = self._photo_key
        # Chave nova a cada quadro (o Qt guarda cache por endereço); o "." final
        # impede que drop("…1.") apague "…10.".
        self._photo_key = f"{self._prefix}{next(self._shots)}."
        self._photo = images.put(self._photo_key, data)
        if old:
            images.drop(old)  # só o quadro mostrado fica na memória
        self.changed.emit()

    async def _vector_of_new_photo(self):
        if self._frame is not None:
            image = self._frame  # exatamente o que está na tela
        else:
            image = await self._camera.capture()
            if self._closed:
                return None
            self._show_photo(image.data)
        self._show("Analisando a foto…")
        embedder = await self._get_embedder()
        vector = await asyncio.to_thread(embedder.embed, image.data)
        return None if self._closed else vector

    async def _add_photo(self, row: int) -> None:
        vector = await self._vector_of_new_photo()
        if vector is None:
            return
        self._classifier.add(row, vector)
        photos = self._classes.rows[row]["photos"] + 1
        self._classes.update(row, photos=photos)
        name = self._classes.rows[row]["name"]
        self._show(f'"{name}": {photos} foto(s). Continue ou toque em Treinar.')

    async def _test(self) -> None:
        vector = await self._vector_of_new_photo()
        if vector is None:
            return
        confidences = self._classifier.predict(vector)
        best = max(confidences, key=confidences.get)
        for row in range(self._classes.rowCount()):
            self._classes.update(row, confidence=confidences.get(row, 0.0), winner=row == best)
        self._show(f"Parece ser: {self._classes.rows[best]['name']}")

    def _show(self, status: str, *, error: bool = False) -> None:
        self._status, self._error = status, error
        self.changed.emit()
