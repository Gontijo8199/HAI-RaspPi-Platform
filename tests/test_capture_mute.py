"""Testes do gating de microfone: pausa/resume e descarte sob mute."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_stream(**kwargs):
    """WhisperStream com MicrophoneStream/VAD/Whisper todos mockados."""
    with (
        patch("stt.capture.MicrophoneStream") as mock_mic_cls,
        patch("stt.capture.SileroVAD") as mock_vad_cls,
        patch("stt.capture.WhisperEngine") as mock_asr_cls,
    ):
        from stt.capture import WhisperStream

        stream = WhisperStream(**kwargs)
    return stream, mock_mic_cls.return_value, mock_vad_cls.return_value, mock_asr_cls.return_value


@pytest.mark.asyncio
async def test_pause_pausa_o_microfone():
    stream, mic, vad, _asr = _make_stream()

    stream.pause()

    mic.pause.assert_called_once()
    assert stream._muted is True
    vad.reset_state.assert_called()


@pytest.mark.asyncio
async def test_pause_cancela_transcricao_parcial_em_andamento():
    stream, mic, _vad, _asr = _make_stream()
    interim = asyncio.create_task(asyncio.sleep(5))
    stream._interim_task = interim
    await asyncio.sleep(0)  # deixa a task iniciar

    stream.pause()
    await asyncio.sleep(0.01)

    assert interim.done()  # cancelada pela pausa
    mic.pause.assert_called_once()


@pytest.mark.asyncio
async def test_resume_retoma_a_captura():
    stream, mic, _vad, _asr = _make_stream()
    stream.pause()

    stream.resume()

    mic.resume.assert_called_once()
    assert stream._muted is False


@pytest.mark.asyncio
async def test_transcricao_final_enfileirada_sem_mute():
    stream, _mic, _vad, asr = _make_stream()
    asr.transcribe = AsyncMock(return_value="quanto é dois mais dois")

    await stream._transcribe_final(b"\x00" * 512)

    asr.transcribe.assert_awaited_once()
    assert not stream._utterance_queue.empty()


@pytest.mark.asyncio
async def test_transcricao_final_descartada_quando_mutado():
    """Áudio transcrito durante a pausa não vira utterance fantasma."""
    stream, _mic, _vad, asr = _make_stream()
    asr.transcribe = AsyncMock(return_value="fala capturada antes da pausa")
    stream._muted = True

    await stream._transcribe_final(b"\x00" * 512)

    asr.transcribe.assert_awaited_once()  # o Whisper até rodou...
    assert stream._utterance_queue.empty()  # ...mas o resultado foi descartado


@pytest.mark.asyncio
async def test_stop_encerra_microfone():
    stream, mic, _vad, _asr = _make_stream()

    stream.stop()

    mic.stop.assert_called_once()
