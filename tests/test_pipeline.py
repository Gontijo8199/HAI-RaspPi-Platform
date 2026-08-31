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


# ---------- Controle: run_turn / cancel_active / busy ----------


@pytest.mark.asyncio
async def test_run_turn_aguarda_o_fim_do_turno(pipeline):
    await pipeline.run_turn("explica frações")

    assert not pipeline.busy


@pytest.mark.asyncio
async def test_run_turn_ignora_utterance_invalida(mock_llm_client, mock_tts):
    from core.pipeline import HAIPipeline

    pipeline = HAIPipeline(llm_client=mock_llm_client, tts=mock_tts)
    await pipeline.run_turn("   !!!   ")

    mock_llm_client.send_stream.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_active_interrompe_o_turno_em_andamento(mock_llm_client, mock_tts):
    from core.pipeline import HAIPipeline

    stream_iniciado = asyncio.Event()

    async def _slow_stream(text):
        stream_iniciado.set()
        for _ in range(200):
            await asyncio.sleep(0.01)
            yield "x"

    mock_llm_client.send_stream = MagicMock(side_effect=_slow_stream)
    pipeline = HAIPipeline(llm_client=mock_llm_client, tts=mock_tts)

    turn = asyncio.create_task(pipeline.run_turn("pergunta longa"))
    await asyncio.wait_for(stream_iniciado.wait(), timeout=1.0)
    assert pipeline.busy

    assert pipeline.cancel_active() is True
    with pytest.raises(asyncio.CancelledError):
        await turn

    mock_llm_client.cancel_stream.assert_called()
    mock_tts.stop_speaking.assert_called()
    assert not pipeline.busy


@pytest.mark.asyncio
async def test_cancel_active_sem_turno_e_noop_e_retorna_false(pipeline):
    assert pipeline.cancel_active() is False


@pytest.mark.asyncio
async def test_busy_reflete_tasks_ativas(pipeline):
    liberar = asyncio.Event()

    async def _bloqueante(text):
        await liberar.wait()
        yield "ok"

    pipeline._llm.send_stream = MagicMock(side_effect=_bloqueante)

    pipeline.process_utterance("oi")
    await asyncio.sleep(0.01)
    assert pipeline.busy is True

    liberar.set()
    await pipeline.wait_pending()
    assert pipeline.busy is False


@pytest.mark.asyncio
async def test_reset_trigger_via_run_turn(mock_llm_client, mock_tts, mock_display):
    from core.pipeline import HAIPipeline

    pipeline = HAIPipeline(llm_client=mock_llm_client, tts=mock_tts, display=mock_display)
    await pipeline.run_turn("resetar")

    mock_llm_client.resetar_sessao.assert_called_once()
    mock_display.clear.assert_called_once()
