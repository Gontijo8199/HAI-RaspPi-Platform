import asyncio
from unittest.mock import MagicMock, patch

import pytest


def _make_speaker(backend="espeak"):
    from tts.speaker import TTSSpeaker

    with patch("tts.speaker.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stdout = MagicMock()
        mock_popen.return_value = mock_proc
        speaker = TTSSpeaker(backend=backend)
    return speaker


def test_speak_enfileira_texto():
    from tts.speaker import TTSSpeaker

    with patch("tts.speaker.subprocess.Popen"):
        speaker = TTSSpeaker(backend="espeak")
        speaker.speak("Olá aluno")
        assert not speaker._queue.empty()
        speaker.shutdown()


def test_speak_ignora_texto_vazio():
    from tts.speaker import TTSSpeaker

    with patch("tts.speaker.subprocess.Popen"):
        speaker = TTSSpeaker(backend="espeak")
        speaker.speak("   ")
        assert speaker._queue.empty()
        speaker.shutdown()


def test_stop_speaking_limpa_fila():
    from tts.speaker import TTSSpeaker

    with patch("tts.speaker.subprocess.Popen"):
        speaker = TTSSpeaker(backend="espeak")
        for i in range(5):
            speaker._queue.put(f"frase {i}")
        speaker.stop_speaking()
        from tts.speaker import _INTERRUPT

        items = []
        while not speaker._queue.empty():
            items.append(speaker._queue.get_nowait())
        assert all(i is _INTERRUPT for i in items) or len(items) == 0
        speaker.shutdown()


@pytest.mark.asyncio
async def test_speak_stream_agrupa_frases():
    from tts.speaker import TTSSpeaker

    enfileirados = []

    async def token_gen():
        for t in ["Olá", ",", " como", " vai", "?", " Tudo", " bem", "."]:
            yield t

    with patch("tts.speaker.subprocess.Popen"):
        speaker = TTSSpeaker(backend="espeak")
        speaker.speak = lambda text: enfileirados.append(text)
        await speaker.speak_stream(token_gen())
        speaker.shutdown()

    assert len(enfileirados) >= 1
    assert all(isinstance(f, str) and len(f) > 0 for f in enfileirados)
