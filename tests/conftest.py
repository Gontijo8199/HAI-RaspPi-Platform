from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def settings():
    return {
        "api": {"model": "gemma-4-26b-a4b-it"},
        "stt": {
            "language": "pt",
            "whisper_model": "tiny",
            "whisper_device": "cpu",
            "whisper_compute_type": "int8",
        },
        "vad": {
            "threshold": 0.5,
            "preroll_ms": 500,
            "silence_ms": 700,
            "interim_interval_ms": 1500,
        },
        "tts": {
            "backend": "espeak",
            "piper_bin": "/opt/piper/piper/piper",
            "piper_model": "/opt/piper/voices/pt_BR-faber-medium.onnx",
            "rate": 160,
            "lang": "pt-br",
        },
    }


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.send = AsyncMock(return_value="Resposta de teste.")

    async def _fake_stream(text):
        for token in ["Resposta ", "de ", "teste."]:
            yield token

    client.send_stream = MagicMock(side_effect=_fake_stream)
    return client


@pytest.fixture
def mock_tts():
    tts = MagicMock()
    tts.speak = MagicMock()
    tts.stop_speaking = MagicMock()
    tts.shutdown = MagicMock()
    tts.speak_stream = AsyncMock()
    return tts
