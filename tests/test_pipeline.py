import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def pipeline(mock_llm_client, mock_tts):
    from core.pipeline import HAIPipeline

    return HAIPipeline(llm_client=mock_llm_client, tts=mock_tts)


@pytest.mark.asyncio
async def test_process_utterance_valida(pipeline, mock_llm_client):
    pipeline.process_utterance("quanto é dois mais dois?")
    await pipeline.wait_pending()

    mock_llm_client.send_stream.assert_called()


@pytest.mark.asyncio
async def test_process_utterance_vazia_ignorada(pipeline, mock_llm_client):
    pipeline.process_utterance("   ")
    await pipeline.wait_pending()

    mock_llm_client.send_stream.assert_not_called()


@pytest.mark.asyncio
async def test_reset_trigger(pipeline, mock_llm_client, mock_tts):
    pipeline.process_utterance("resetar")
    await pipeline.wait_pending()

    mock_llm_client.send_stream.assert_not_called()
    mock_tts.stop_speaking.assert_called_once()


@pytest.mark.asyncio
async def test_process_utterance_chama_tts(pipeline, mock_tts):
    pipeline.process_utterance("explica fotossíntese")
    await pipeline.wait_pending()

    mock_tts.speak.assert_called()


@pytest.mark.asyncio
async def test_wait_pending_sem_tasks(pipeline):
    await pipeline.wait_pending()


@pytest.fixture
def pipeline_com_display(mock_llm_client, mock_tts, mock_display):
    from core.pipeline import HAIPipeline

    return HAIPipeline(llm_client=mock_llm_client, tts=mock_tts, display=mock_display)


@pytest.mark.asyncio
async def test_resposta_completa_vai_para_o_display(pipeline_com_display, mock_display):
    pipeline_com_display.process_utterance("explica fotossíntese")
    await pipeline_com_display.wait_pending()

    mock_display.show_response.assert_called_once()
    (texto_exibido,), _ = mock_display.show_response.call_args
    assert texto_exibido == "Resposta de teste."


@pytest.mark.asyncio
async def test_flashcard_e_gerado_e_exibido(pipeline_com_display, mock_llm_client, mock_display):
    pipeline_com_display.process_utterance("explica fotossíntese")
    await pipeline_com_display.wait_pending()

    mock_llm_client.generate_flashcard.assert_called_once_with("explica fotossíntese")
    mock_display.show_flashcard.assert_called_once()
    (flashcard_md,), _ = mock_display.show_flashcard.call_args
    assert "Tópico de teste" in flashcard_md


@pytest.mark.asyncio
async def test_sem_display_nao_gera_flashcard(pipeline, mock_llm_client):

    pipeline.process_utterance("explica fotossíntese")
    await pipeline.wait_pending()

    mock_llm_client.generate_flashcard.assert_not_called()


@pytest.mark.asyncio
async def test_reset_trigger_limpa_o_display(pipeline_com_display, mock_display, mock_tts):
    pipeline_com_display.process_utterance("resetar")
    await pipeline_com_display.wait_pending()

    mock_display.clear.assert_called_once()
    mock_tts.stop_speaking.assert_called_once()


@pytest.mark.asyncio
async def test_falha_no_flashcard_nao_derruba_resposta(
    pipeline_com_display, mock_llm_client, mock_display
):
    mock_llm_client.generate_flashcard = AsyncMock(side_effect=RuntimeError("boom"))

    pipeline_com_display.process_utterance("explica fotossíntese")
    await pipeline_com_display.wait_pending()

    mock_display.show_response.assert_called_once()
    mock_display.show_flashcard.assert_not_called()


@pytest.mark.asyncio
async def test_display_fn_legado_continua_funcionando(mock_llm_client, mock_tts):
    from core.pipeline import HAIPipeline

    recebido = []
    pipeline_legado = HAIPipeline(
        llm_client=mock_llm_client,
        tts=mock_tts,
        display_fn=recebido.append,
    )

    pipeline_legado.process_utterance("explica fotossíntese")
    await pipeline_legado.wait_pending()

    assert recebido == ["Resposta de teste."]
