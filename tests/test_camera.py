import sys

import cv2
import numpy as np
import pytest

from vision.camera import CameraCapture, CameraError, _encode_jpeg, _open_capture


def _frame(height=720, width=1280):
    gradiente = np.linspace(0, 255, width, dtype=np.uint8)
    return np.repeat(np.tile(gradiente, (height, 1))[:, :, None], 3, axis=2)


class FakeCap:
    """Substitui cv2.VideoCapture: entrega os frames dados e depois falha."""

    def __init__(self, frames=(), opened=True):
        self._frames = list(frames)
        self._opened = opened
        self.reads = 0
        self.released = False

    def isOpened(self):
        return self._opened

    def read(self):
        self.reads += 1
        if self._frames:
            return True, self._frames.pop(0)
        return False, None

    def release(self):
        self.released = True


@pytest.fixture
def fake_open(monkeypatch):
    """Instala um FakeCap como resultado de _open_capture e o devolve."""

    def _install(cap):
        monkeypatch.setattr("vision.camera._open_capture", lambda *_a, **_k: cap)
        return cap

    return _install


def _decode(jpeg: bytes):
    return cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)


class TestEncodeJpeg:
    def test_reduz_mantendo_proporcao(self):
        data, width, height = _encode_jpeg(_frame(720, 1280), max_side=640, quality=85)

        assert data[:2] == b"\xff\xd8"  # assinatura JPEG
        assert (width, height) == (640, 360)
        assert _decode(data).shape[:2] == (360, 640)

    def test_nao_amplia_imagem_pequena(self):
        _data, width, height = _encode_jpeg(_frame(240, 320), max_side=1024, quality=85)

        assert (width, height) == (320, 240)

    def test_qualidade_menor_gera_arquivo_menor(self):
        alto, _, _ = _encode_jpeg(_frame(), max_side=1024, quality=95)
        baixo, _, _ = _encode_jpeg(_frame(), max_side=1024, quality=30)

        assert len(baixo) < len(alto)


class TestCapture:
    async def test_captura_e_devolve_jpeg_reduzido(self, fake_open):
        cap = fake_open(FakeCap([_frame()] * 3))
        camera = CameraCapture(warmup_frames=2, max_side=640)

        image = await camera.capture()

        assert image.mime_type == "image/jpeg"
        assert image.data[:2] == b"\xff\xd8"
        assert (image.width, image.height) == (640, 360)
        assert cap.reads == 3  # 2 de aquecimento + 1 final
        assert cap.released is True

    async def test_usa_o_ultimo_frame_bom_se_faltar_frame(self, fake_open):
        cap = fake_open(FakeCap([_frame()] * 2))  # só 2 frames para 5 leituras
        camera = CameraCapture(warmup_frames=4)

        image = await camera.capture()

        assert image.width > 0
        assert cap.released is True

    async def test_camera_que_nao_abre_lanca_e_libera(self, fake_open):
        cap = fake_open(FakeCap(opened=False))

        with pytest.raises(CameraError, match="abrir a câmera"):
            await CameraCapture(device="/dev/video9").capture()

        assert cap.released is True

    async def test_camera_sem_frames_lanca(self, fake_open):
        cap = fake_open(FakeCap([]))

        with pytest.raises(CameraError, match="nenhum frame"):
            await CameraCapture(warmup_frames=1).capture()

        assert cap.released is True

    async def test_grava_em_disco_so_com_save_dir(self, fake_open, tmp_path):
        fake_open(FakeCap([_frame()] * 2))
        image = await CameraCapture(warmup_frames=1, save_dir=tmp_path / "fotos").capture()

        assert image.path is not None
        assert image.path.read_bytes() == image.data

    async def test_sem_save_dir_nada_vai_para_o_disco(self, fake_open, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fake_open(FakeCap([_frame()] * 2))

        image = await CameraCapture(warmup_frames=1).capture()

        assert image.path is None
        assert list(tmp_path.iterdir()) == []

    async def test_falha_ao_gravar_nao_derruba_a_captura(self, fake_open, tmp_path):
        arquivo = tmp_path / "ocupado"
        arquivo.write_text("x")  # save_dir apontando para um arquivo → mkdir falha
        fake_open(FakeCap([_frame()] * 2))

        image = await CameraCapture(warmup_frames=1, save_dir=arquivo).capture()

        assert image.path is None
        assert image.data


class TestProbe:
    def test_probe_true_quando_abre(self, fake_open):
        cap = fake_open(FakeCap([_frame()]))

        assert CameraCapture().probe() is True
        assert cap.released is True

    def test_probe_false_quando_nao_abre(self, fake_open):
        fake_open(FakeCap(opened=False))

        assert CameraCapture().probe() is False


class TestSemOpenCV:
    def test_open_capture_sem_cv2_lanca_camera_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "cv2", None)  # força ImportError

        with pytest.raises(CameraError, match="OpenCV"):
            _open_capture(0, 640, 480)

    def test_probe_sem_cv2_retorna_false(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "cv2", None)

        assert CameraCapture().probe() is False
