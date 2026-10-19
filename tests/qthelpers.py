"""Utilitários dos testes de interface (Qt Quick de verdade, plataforma offscreen)."""

import asyncio

from PySide6.QtCore import QCoreApplication, QPointF, Qt
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


async def pump(seconds=0.05):
    """Roda o Qt e o asyncio juntos por `seconds` (timers, animações, tarefas)."""
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while True:
        QCoreApplication.processEvents()
        await asyncio.sleep(0.005)
        if loop.time() >= end:
            break
    QCoreApplication.processEvents()


async def until(predicate, timeout=5.0):
    """Espera a condição. 5 s: a primeira carga da QML depois de editá-la recompila
    o cache, e o primeiro teclado da sessão leva mais de 2 s para aparecer."""
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError("condição não atingida a tempo")
        QCoreApplication.processEvents()
        await asyncio.sleep(0.005)


def items(window):
    """Todos os itens visuais da janela (inclusive popups abertos), em ordem."""
    out = []

    def walk(item: QQuickItem):
        out.append(item)
        for child in item.childItems():
            walk(child)

    walk(window.contentItem())
    return out


def screen_items(window):
    """Itens das telas, sem os do teclado da tela: os internos dele mudam com o
    layout carregado (letras, números) e não dizem nada sobre vazamento."""
    keyboard = [i for i in items(window) if i.objectName() == "keyboardLoader"]
    skip = set()
    for root in keyboard:
        stack = [root]
        while stack:
            item = stack.pop()
            skip.add(id(item))
            stack.extend(item.childItems())
    return [i for i in items(window) if id(i) not in skip]


def find(window, name):
    """Item visível com esse objectName (None se não houver)."""
    return next((i for i in items(window) if i.objectName() == name and shown(i)), None)


def find_all(window, prefix):
    return [i for i in items(window) if i.objectName().startswith(prefix) and shown(i)]


def shown(item) -> bool:
    """Visível de fato: ele e todos os ancestrais."""
    return bool(item.isVisible())


def center(item):
    return item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()


def click(window, item, pos=None):
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     pos or center(item))  # fmt: skip


def press(window, item):
    QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     center(item))  # fmt: skip


def release(window, item):
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       center(item))  # fmt: skip


def key(window, key, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(window, key, modifiers)


def type_text(window, text):
    """Digita como um teclado físico (uma tecla por caractere)."""
    for char in text:
        QTest.keyClick(window, char)


def label(item) -> str:
    return item.property("text") or ""
