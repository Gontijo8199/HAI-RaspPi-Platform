"""
Imagem capturada pela câmera, pronta para anexar a um prompt do LLM.

Módulo sem dependências (nem OpenCV): só bytes + metadados. Assim o cliente
LLM e os módulos podem tipar/receber imagens sem importar a camada de câmera.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CapturedImage:
    """JPEG já redimensionado/comprimido.

    Atributos
    ---------
    data : bytes
        Conteúdo do arquivo JPEG.
    width, height : int
        Dimensões finais (após o resize).
    mime_type : str
        Tipo MIME enviado ao LLM.
    captured_at : float
        time.monotonic() do momento da captura (usado para expirar a foto pendente).
    path : Path | None
        Onde a foto foi gravada, se [camera] save_dir estiver configurado.
    """

    data: bytes
    width: int
    height: int
    mime_type: str = "image/jpeg"
    captured_at: float = field(default_factory=time.monotonic)
    path: Path | None = None

    @property
    def size_kb(self) -> float:
        return len(self.data) / 1024
