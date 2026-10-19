"""
Imagens servidas à QML pelo endereço "image://hai/...":

- "image://hai/photo/<chave>": uma foto da câmera (JPEG em memória). O Qt lê o
  JPEG direto e reduz ao tamanho pedido (sourceSize na QML; largura/altura da
  imagem embutida no editor).
- "image://hai/pending/<chave>/<rótulo>": a pílula "gravando…", "tirando foto…"
  que reserva, no editor, o lugar onde o conteúdo vai entrar.

As fotos ficam só na memória, enquanto a conversa existir: cada tela as
registra com put() e as solta com drop() ao sair ou ao apagar a conversa.
O dicionário é do processo; cada QQmlEngine recebe um ImageStore (o motor
apaga o provider junto com ele), e todos leem o mesmo dicionário.
A chave leva um prefixo por entrada no módulo, porque o Qt guarda em cache
as imagens por endereço e os ids de bloco recomeçam a cada conversa.
"""

from __future__ import annotations

import threading
from urllib.parse import quote, unquote

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen
from PySide6.QtQuick import QQuickImageProvider

from ui import theme

PROVIDER = "hai"
PILL_HEIGHT = 40
_PILL_FONT_PX = theme.FONT_PX["small"]


def photo_url(key: str) -> str:
    return f"image://{PROVIDER}/photo/{key}"


def pending_url(key: str, label: str) -> str:
    return f"image://{PROVIDER}/pending/{key}/{quote(label)}"


def pill_size(label: str) -> QSize:
    """Tamanho da pílula de um rótulo (o editor reserva esse espaço)."""
    font = QFont()
    font.setPixelSize(_PILL_FONT_PX)
    width = QFontMetrics(font).horizontalAdvance(label) + 28
    return QSize(width, PILL_HEIGHT)


_lock = threading.Lock()  # o Qt pode pedir imagens de outra thread
_photos: dict[str, bytes] = {}


def put(key: str, jpeg: bytes) -> str:
    """Registra uma foto e devolve o endereço dela para a QML."""
    with _lock:
        _photos[key] = jpeg
    return photo_url(key)


def drop(prefix: str) -> None:
    """Esquece as fotos cuja chave começa com `prefix`."""
    with _lock:
        for key in [k for k in _photos if k.startswith(prefix)]:
            del _photos[key]


def stored() -> int:
    return len(_photos)


class ImageStore(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, image_id: str, size: QSize, requested: QSize) -> QImage:  # noqa: N802
        kind, _, rest = image_id.partition("/")
        if kind == "pending":
            _key, _, label = rest.partition("/")
            return _pill(unquote(label))
        with _lock:
            data = _photos.get(rest)
        image = QImage.fromData(data) if data else QImage()
        if image.isNull():
            return _missing(requested)
        if requested.isValid() and (requested.width() > 0 or requested.height() > 0):
            target = QSize(
                requested.width() if requested.width() > 0 else image.width(),
                requested.height() if requested.height() > 0 else image.height(),
            )
            image = image.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return image


def _pill(label: str) -> QImage:
    size = pill_size(label)
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(theme.BORDER), 1))
    painter.setBrush(QColor(theme.DISABLED_BG))
    rect = QRectF(0.5, 4.5, size.width() - 1, size.height() - 9)
    painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
    font = QFont()
    font.setPixelSize(_PILL_FONT_PX)
    font.setItalic(True)
    painter.setFont(font)
    painter.setPen(QColor(theme.MUTED))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
    painter.end()
    return image


def _missing(requested: QSize) -> QImage:
    """Foto que não decodifica: um quadro neutro no lugar (a interface não quebra)."""
    side = max(requested.width(), requested.height(), 48)
    image = QImage(side, side, QImage.Format.Format_RGB32)
    image.fill(QColor(theme.DISABLED_BG))
    return image
