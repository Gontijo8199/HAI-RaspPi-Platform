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
