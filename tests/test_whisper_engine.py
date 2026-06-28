import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@patch("stt.whisper_engine.WhisperModel")
def test_transcribe_retorna_texto(mock_whisper):
    seg1, seg2 = MagicMock(), MagicMock()
    seg1.text = "quanto"
    seg2.text = "é dois mais dois"
    mock_whisper.return_value.transcribe.return_value = ([seg1, seg2], MagicMock())

    from stt.whisper_engine import WhisperEngine

    engine = WhisperEngine(model_size="tiny")
    pcm = np.zeros(16000, dtype=np.int16).tobytes()
    result = asyncio.run(engine.transcribe(pcm))

    assert result == "quanto é dois mais dois"


@patch("stt.whisper_engine.WhisperModel")
def test_transcribe_vazio(mock_whisper):
    """Sem segmentos retorna string vazia."""
    mock_whisper.return_value.transcribe.return_value = ([], MagicMock())

    from stt.whisper_engine import WhisperEngine

    engine = WhisperEngine(model_size="tiny")
    pcm = np.zeros(16000, dtype=np.int16).tobytes()
    result = asyncio.run(engine.transcribe(pcm))

    assert result == ""


@patch("stt.whisper_engine.WhisperModel")
def test_transcribe_strip_espacos(mock_whisper):
    seg = MagicMock()
    seg.text = "  olá mundo  "
    mock_whisper.return_value.transcribe.return_value = ([seg], MagicMock())

    from stt.whisper_engine import WhisperEngine

    engine = WhisperEngine(model_size="tiny")
    pcm = np.zeros(16000, dtype=np.int16).tobytes()
    result = asyncio.run(engine.transcribe(pcm))

    assert result == "olá mundo"


@patch("stt.whisper_engine.WhisperModel")
def test_transcribe_parametros_passados(mock_whisper):
    mock_whisper.return_value.transcribe.return_value = ([], MagicMock())

    from stt.whisper_engine import WhisperEngine

    engine = WhisperEngine(model_size="tiny", beam_size=1)
    pcm = np.zeros(16000, dtype=np.int16).tobytes()
    asyncio.run(engine.transcribe(pcm))

    call_kwargs = mock_whisper.return_value.transcribe.call_args[1]
    assert call_kwargs["vad_filter"] is True
    assert call_kwargs["beam_size"] == 1
    assert call_kwargs["word_timestamps"] is False
