"""Fotos no pipeline: gatilho de voz, foto pendente, TTL e preservação em cancel/erro."""

import asyncio
from unittest.mock import MagicMock

import pytest

from core.pipeline import HAIPipeline, parse_photo_request
from vision.camera import CameraError
from vision.image import CapturedImage


@pytest.fixture
def pipeline(mock_llm_client, mock_tts, mock_display, mock_camera):
    return HAIPipeline(
        llm_client=mock_llm_client, tts=mock_tts, display=mock_display, camera=mock_camera
    )


class TestParsePhotoRequest:
    @pytest.mark.parametrize(
        "fala,esperado",
        [
            ("tira uma foto", (True, False)),
            ("Tira uma foto, por favor.", (True, False)),
            ("tira uma foto disso", (True, False)),
            ("olha isso", (True, False)),
            ("Usa a câmera", (True, False)),
            ("Olha isso, que planta é essa?", (True, True)),
            ("tira foto e me diz o que é", (True, True)),
            ("o que é isso aqui? olha essa folha", (True, True)),
        ],
    )
    def test_detecta_gatilho(self, fala, esperado):
        assert parse_photo_request(fala) == esperado

    @pytest.mark.parametrize(
        "fala",
        [
            "explica fotossíntese",
            "o que é uma foto?",
            "olha só",
            "quanto é dois mais dois",
        ],
    )
    def test_fala_comum_nao_dispara(self, fala):
        assert parse_photo_request(fala) == (False, True)


class TestGatilhoPorVoz:
    async def test_gatilho_com_pergunta_captura_e_envia_foto(
        self, pipeline, mock_camera, mock_llm_client, fake_image
    ):
        await pipeline.run_turn("olha isso, que planta é essa?")

        mock_camera.capture.assert_awaited_once()
        mock_llm_client.send_stream.assert_called_once_with(
            "olha isso, que planta é essa?", images=[fake_image]
        )
        assert not pipeline.has_pending_photo  # consumida após a resposta

    async def test_flashcard_tambem_recebe_a_foto(self, pipeline, mock_llm_client, fake_image):
        await pipeline.run_turn("olha isso, que planta é essa?")

        mock_llm_client.generate_flashcard.assert_called_once_with(
            "olha isso, que planta é essa?", images=[fake_image]
        )

    async def test_so_o_gatilho_captura_avisa_e_espera_a_pergunta(
        self, pipeline, mock_camera, mock_llm_client, mock_tts
    ):
        await pipeline.run_turn("tira uma foto")

        mock_camera.capture.assert_awaited_once()
        mock_llm_client.send_stream.assert_not_called()
        mock_tts.speak.assert_called_once()
        assert "tirei a foto" in mock_tts.speak.call_args.args[0]
        assert pipeline.has_pending_photo

    async def test_pergunta_seguinte_leva_a_foto_pendente_e_a_consome(
        self, pipeline, mock_llm_client, fake_image
    ):
        await pipeline.run_turn("tira uma foto")

        await pipeline.run_turn("que planta é essa?")
        mock_llm_client.send_stream.assert_called_with("que planta é essa?", images=[fake_image])
        assert not pipeline.has_pending_photo

        await pipeline.run_turn("e para que serve?")
        mock_llm_client.send_stream.assert_called_with("e para que serve?")  # sem foto

    async def test_falha_da_camera_avisa_e_nao_chama_o_llm(
        self, pipeline, mock_camera, mock_llm_client, mock_tts
    ):
        mock_camera.capture.side_effect = CameraError("não abriu")

        await pipeline.run_turn("olha isso, o que é?")

        mock_llm_client.send_stream.assert_not_called()
        assert "câmera" in mock_tts.speak.call_args.args[0]
        assert not pipeline.has_pending_photo

    async def test_sem_camera_o_gatilho_e_fala_comum(self, mock_llm_client, mock_tts):
        pipeline = HAIPipeline(llm_client=mock_llm_client, tts=mock_tts)

        await pipeline.run_turn("olha isso, que planta é essa?")

        mock_llm_client.send_stream.assert_called_once_with("olha isso, que planta é essa?")


class TestFotoPendente:
    async def test_capture_photo_deixa_pendente(self, pipeline, mock_camera):
        assert await pipeline.capture_photo() is True

        assert pipeline.has_pending_photo
        mock_camera.capture.assert_awaited_once()

    async def test_foto_nova_substitui_a_pendente(self, pipeline, mock_camera, mock_llm_client):
        primeira = CapturedImage(data=b"1", width=1, height=1)
        segunda = CapturedImage(data=b"2", width=1, height=1)
        mock_camera.capture.side_effect = [primeira, segunda]

        await pipeline.capture_photo()
        await pipeline.capture_photo()
        await pipeline.run_turn("o que é isso?")

        mock_llm_client.send_stream.assert_called_once_with("o que é isso?", images=[segunda])

    async def test_foto_expira_apos_o_ttl(self, mock_llm_client, mock_tts, mock_camera):
        pipeline = HAIPipeline(
            llm_client=mock_llm_client, tts=mock_tts, camera=mock_camera, photo_ttl_s=0.0
        )
        await pipeline.capture_photo()
        await asyncio.sleep(0.01)

        assert not pipeline.has_pending_photo
        await pipeline.run_turn("o que é isso?")
        mock_llm_client.send_stream.assert_called_once_with("o que é isso?")

    async def test_discard_photo(self, pipeline):
        assert pipeline.discard_photo() is False  # nada a descartar

        await pipeline.capture_photo()

        assert pipeline.discard_photo() is True
        assert not pipeline.has_pending_photo

    async def test_falha_de_captura_mantem_a_foto_anterior(self, pipeline, mock_camera):
        await pipeline.capture_photo()
        mock_camera.capture.side_effect = CameraError("boom")

        assert await pipeline.capture_photo() is False
        assert pipeline.has_pending_photo  # a boa anterior continua valendo

    async def test_request_photo_dispara_a_captura(self, pipeline, mock_camera):
        pipeline.request_photo()
        await asyncio.gather(*pipeline._photo_tasks)

        mock_camera.capture.assert_awaited_once()
        assert pipeline.has_pending_photo

    async def test_request_photo_ignorada_com_turno_em_andamento(
        self, pipeline, mock_camera, mock_llm_client
    ):
        liberar = asyncio.Event()

        async def _bloqueante(text, images=None):
            await liberar.wait()
            yield "ok"

        mock_llm_client.send_stream = MagicMock(side_effect=_bloqueante)
        pipeline.process_utterance("explica frações")
        await asyncio.sleep(0.01)
        assert pipeline.busy

        pipeline.request_photo()
        await asyncio.sleep(0.01)
        mock_camera.capture.assert_not_awaited()

        liberar.set()
        await pipeline.wait_pending()

    async def test_request_photo_sem_camera_e_noop(self, mock_llm_client, mock_tts):
        pipeline = HAIPipeline(llm_client=mock_llm_client, tts=mock_tts)

        pipeline.request_photo()

        assert not pipeline._photo_tasks


class TestFotoPreservada:
    async def test_cancelar_o_turno_preserva_a_foto(
        self, pipeline, mock_llm_client, mock_camera, fake_image
    ):
        iniciado = asyncio.Event()

        async def _lento(text, images=None):
            iniciado.set()
            for _ in range(200):
                await asyncio.sleep(0.01)
                yield "x"

        mock_llm_client.send_stream = MagicMock(side_effect=_lento)
        await pipeline.capture_photo()

        turno = asyncio.create_task(pipeline.run_turn("que planta é essa?"))
        await asyncio.wait_for(iniciado.wait(), timeout=1.0)
        pipeline.cancel_active()
        with pytest.raises(asyncio.CancelledError):
            await turno

        assert pipeline.has_pending_photo

    async def test_erro_de_api_preserva_a_foto(self, pipeline, mock_llm_client):
        async def _falha(text, images=None):
            raise RuntimeError("boom")
            yield  # pragma: no cover  (torna a função um gerador)

        mock_llm_client.send_stream = MagicMock(side_effect=_falha)
        await pipeline.capture_photo()

        await pipeline.run_turn("que planta é essa?")

        assert pipeline.has_pending_photo
