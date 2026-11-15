"""
Extrator de características de imagem: MobileNetV2 (ONNX) no onnxruntime.

Transforma uma foto JPEG num vetor de tamanho 1 que a lógica (logic.py) compara
por cosseno. O modelo não é versionado: baixe uma vez (≈14 MB, precisa de internet)::

    python -m modules.treinar_imagem.embedder --download

Falhas (modelo ausente, onnxruntime faltando, foto que não decodifica) viram
EmbedderError, com mensagem legível para a tela.
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "mobilenetv2.onnx"
MODEL_URL = (
    "https://github.com/onnx/models/raw/main/validated/vision/classification/"
    "mobilenet/model/mobilenetv2-12.onnx"
)
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)  # normalização ImageNet (RGB)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class EmbedderError(RuntimeError):
    """O extrator não pôde ser carregado ou usado. A mensagem vai para a tela."""


class Embedder:
    def __init__(self, path: Path = MODEL_PATH):
        if not path.exists():
            raise EmbedderError(
                "O modelo de imagem não foi baixado. Rode uma vez (com internet): "
                "python -m modules.treinar_imagem.embedder --download"
            )
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise EmbedderError(f"Não consegui carregar o modelo de imagem ({exc}).") from exc
        spec = self._session.get_inputs()[0]  # [lote, 3, lado, lado] (NCHW)
        self._input = spec.name
        self._side = int(spec.shape[2])

    def embed(self, jpeg: bytes) -> np.ndarray:
        """Vetor normalizado (norma 1) da foto. Bloqueante: chame numa thread."""
        import cv2

        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise EmbedderError("Não consegui ler a foto.")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # o OpenCV decodifica em BGR
        rgb = cv2.resize(rgb, (self._side, self._side), interpolation=cv2.INTER_AREA)
        x = (rgb.astype(np.float32) / 255.0 - _MEAN) / _STD
        x = x.transpose(2, 0, 1)[np.newaxis]
        # shortcut: usa os logits (1000-d) como embedding; trocar pela camada penúltima
        # se a acurácia decepcionar.
        out = self._session.run(None, {self._input: x})[0][0].astype(np.float32)
        norm = float(np.linalg.norm(out))
        return out / norm if norm else out


def _download(path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    print(f"Baixando {MODEL_URL}")
    urllib.request.urlretrieve(MODEL_URL, partial)
    partial.replace(path)  # só aparece com o nome final se o download terminou
    print(f"Salvo em {path}")


def _main() -> None:
    parser = argparse.ArgumentParser(description="Modelo do módulo Treinar reconhecedor")
    parser.add_argument("--download", action="store_true", help="Baixa o modelo (≈14 MB).")
    args = parser.parse_args()
    if args.download:
        _download()
    embedder = Embedder()
    spec = embedder._session.get_inputs()[0]
    print(f"OK: entrada {spec.name} {spec.shape}")


if __name__ == "__main__":
    _main()
