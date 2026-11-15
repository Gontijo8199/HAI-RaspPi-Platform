"""MobileNetV2 de verdade (pulado sem models/mobilenetv2.onnx: baixe com
python -m modules.treinar_imagem.embedder --download)."""

import numpy as np
import pytest
from fakes import _image

from modules.treinar_imagem.embedder import MODEL_PATH, Embedder, EmbedderError

pytestmark = pytest.mark.skipif(not MODEL_PATH.exists(), reason="modelo não baixado")


def test_vetor_normalizado_e_fotos_iguais_sao_identicas():
    embedder = Embedder()
    a, b, other = (embedder.embed(_image(n).data) for n in (1, 1, 5))
    assert a.shape == (1000,) and abs(np.linalg.norm(a) - 1) < 1e-5
    assert a @ b > 0.999 and a @ other < a @ b


def test_foto_corrompida_vira_embedder_error():
    with pytest.raises(EmbedderError):
        Embedder().embed(b"nao e jpeg")
