"""
Captura de foto pela webcam — a mesma usada como microfone (UVC + UAC são
interfaces USB independentes, então abrir o vídeo não atrapalha o PyAudio).

Design (mesmo padrão de stt/audio_stream.py e tts/speaker.py):
- A câmera é aberta SOB DEMANDA: abre, descarta alguns frames (auto-exposição e
  balanço de branco precisam estabilizar), captura 1 frame e fecha. Não mantém
  o dispositivo aberto — poupa CPU/USB no Pi e evita conflito com outros apps.
- capture() é async e roda o OpenCV em asyncio.to_thread: nunca bloqueia o loop.
- Um lock serializa capturas concorrentes (ex.: hotkey apertada duas vezes).
- O frame é reduzido (lado maior = max_side) e comprimido em JPEG antes de sair:
  menos banda e menos tokens de imagem no LLM.
- cv2 é importado tardiamente: sem OpenCV o resto do programa continua de pé e
  só a captura falha (com CameraError, que o pipeline trata).
- Falhas viram CameraError; nada aqui lança exceção "crua" do OpenCV.

Diagnóstico (a partir da raiz do projeto)::

    python -m vision.camera --list              # índices de câmera que abrem
    python -m vision.camera --device 0 -o t.jpg # tira uma foto de teste
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from vision.image import CapturedImage

logger = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Falha ao abrir a câmera ou capturar um frame."""


def _import_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise CameraError("OpenCV não instalado (pip install opencv-python-headless).") from exc
    return cv2


def _open_capture(device: int | str, width: int, height: int) -> Any:
    """Abre o dispositivo de vídeo. Retorna o cv2.VideoCapture (aberto ou não)."""
    cv2 = _import_cv2()
    backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
    cap = cv2.VideoCapture(device, backend)
    if cap.isOpened():
        # MJPG: webcams USB entregam 720p+ com muito mais fps do que em YUYV.
        # Se a câmera não suportar, o set() só retorna False e segue no padrão.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _encode_jpeg(frame: Any, max_side: int, quality: int) -> tuple[bytes, int, int]:
    """Reduz o frame (se maior que max_side) e codifica em JPEG."""
    cv2 = _import_cv2()
    height, width = frame.shape[:2]
    scale = max_side / max(height, width)
    if scale < 1.0:
        frame = cv2.resize(
            frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
        )
        height, width = frame.shape[:2]

    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise CameraError("Falha ao codificar a foto em JPEG.")
    return buffer.tobytes(), width, height


class CameraCapture:
    """Tira fotos com a webcam, de forma não-bloqueante.

    Parâmetros
    ----------
    device : int | str
        Índice do V4L2 (0 → /dev/video0) ou caminho ('/dev/video0'). Em muitas
        webcams o par de nós é /dev/video0 (imagem) + /dev/video1 (metadados):
        use `python -m vision.camera --list` para achar o que entrega frames.
    width, height : int
        Resolução pedida à câmera (a câmera pode escolher a mais próxima).
    max_side : int
        Lado maior (px) da foto enviada ao LLM. 1024 é um bom custo/benefício
        para ler caderno/lousa sem pesar na rede do Pi.
    jpeg_quality : int
        Qualidade do JPEG (1–100).
    warmup_frames : int
        Frames descartados antes do frame final (estabiliza exposição/branco).
    save_dir : str | Path | None
        Se informado, cada foto também é gravada aqui (útil para depurar).
        None/vazio = nada vai para o disco (padrão: privacidade dos alunos).
    read_timeout_s : float
        Tempo máximo lendo frames; estourado, usa o último frame bom (se houver).
    """

    def __init__(
        self,
        device: int | str = 0,
        width: int = 1280,
        height: int = 720,
        max_side: int = 1024,
        jpeg_quality: int = 85,
        warmup_frames: int = 8,
        save_dir: str | Path | None = None,
        read_timeout_s: float = 5.0,
    ):
        self._device = device
        self._width = width
        self._height = height
        self._max_side = max_side
        self._jpeg_quality = jpeg_quality
        self._warmup_frames = max(0, warmup_frames)
        self._save_dir = Path(save_dir) if save_dir else None
        self._read_timeout_s = read_timeout_s
        self._lock = threading.Lock()

    @property
    def device(self) -> int | str:
        return self._device

    async def capture(self) -> CapturedImage:
        """Tira uma foto. Levanta CameraError se a câmera falhar."""
        return await asyncio.to_thread(self._capture_sync)

    def probe(self) -> bool:
        """Abre e fecha a câmera para checar se está acessível (bloqueante)."""
        try:
            with self._lock:
                cap = _open_capture(self._device, self._width, self._height)
                try:
                    return bool(cap.isOpened())
                finally:
                    cap.release()
        except CameraError as exc:
            logger.warning("Câmera indisponível: %s", exc)
            return False

    # Interno

    def _capture_sync(self) -> CapturedImage:
        with self._lock:
            cap = _open_capture(self._device, self._width, self._height)
            try:
                if not cap.isOpened():
                    raise CameraError(
                        f"Não consegui abrir a câmera {self._device!r}. "
                        "Ela está conectada e livre (nenhum outro app usando)?"
                    )
                frame = self._read_stable_frame(cap)
            finally:
                cap.release()

        data, width, height = _encode_jpeg(frame, self._max_side, self._jpeg_quality)
        path = self._save(data)
        image = CapturedImage(data=data, width=width, height=height, path=path)
        logger.info("Foto capturada: %dx%d, %.0f KB", width, height, image.size_kb)
        return image

    def _read_stable_frame(self, cap: Any) -> Any:
        deadline = time.monotonic() + self._read_timeout_s
        frame = None
        for _ in range(self._warmup_frames + 1):
            ok, img = cap.read()
            if ok and img is not None:
                frame = img
            if time.monotonic() > deadline:
                break
        if frame is None:
            raise CameraError("A câmera abriu, mas não entregou nenhum frame.")
        return frame

    def _save(self, data: bytes) -> Path | None:
        if self._save_dir is None:
            return None
        try:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            path = self._save_dir / f"foto-{datetime.now():%Y%m%d-%H%M%S-%f}.jpg"
            path.write_bytes(data)
            return path
        except OSError as exc:
            logger.warning("Não foi possível gravar a foto em disco: %s", exc)
            return None


def _list_devices(max_index: int = 10) -> None:
    print("Procurando câmeras que entregam frames...")
    found = False
    for index in range(max_index):
        cap = _open_capture(index, 640, 480)
        try:
            if cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    found = True
                    print(f"  device = {index}  (/dev/video{index})  OK")
        finally:
            cap.release()
    if not found:
        print("  nenhuma câmera respondeu.")


def _main() -> None:
    parser = argparse.ArgumentParser(description="Teste da câmera do HAI")
    parser.add_argument("--list", action="store_true", help="Lista os índices que abrem.")
    parser.add_argument("--device", default="0", help="Índice (0) ou caminho (/dev/video0).")
    parser.add_argument("-o", "--out", default="foto-teste.jpg", help="Arquivo de saída.")
    args = parser.parse_args()

    if args.list:
        _list_devices()
        return

    device: int | str = int(args.device) if args.device.isdigit() else args.device
    try:
        image = asyncio.run(CameraCapture(device=device).capture())
    except CameraError as exc:
        print(f"Erro: {exc}")
        raise SystemExit(1) from exc
    Path(args.out).write_bytes(image.data)
    print(f"Foto salva em {args.out} ({image.width}x{image.height}, {image.size_kb:.0f} KB)")


if __name__ == "__main__":
    _main()
