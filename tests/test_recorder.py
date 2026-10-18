"""Gravador segurar-para-falar (stt/recorder.py) com o microfone simulado."""

import asyncio
from unittest.mock import MagicMock

import pytest

from stt.recorder import MicrophoneError, VoiceRecorder


class FakeMic:
    instances: list["FakeMic"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.calls: list[str] = []
        FakeMic.instances.append(self)

    def start(self, loop):
        self.calls.append("start")

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")

    def stop(self):
        self.calls.append("stop")

    async def read_chunk(self):
        return await self.queue.get()


async def test_abre_pausado_grava_e_devolve_o_audio():
    rec = VoiceRecorder(min_seconds=0.0, mic_factory=FakeMic)
    rec.open()
    mic = FakeMic.instances[-1]
    assert mic.calls == ["start", "pause"]  # nada é capturado até segurar o botão

    rec.start()
    assert rec.recording
    for chunk in (b"ab", b"cd"):
        mic.queue.put_nowait(chunk)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert await rec.stop() == b"abcd"
    assert mic.calls[-1] == "pause"
    assert not rec.recording


async def test_gravacao_curta_devolve_none():
    rec = VoiceRecorder(min_seconds=0.3, mic_factory=FakeMic)
    rec.open()
    rec.start()
    FakeMic.instances[-1].queue.put_nowait(b"\x00" * 100)
    await asyncio.sleep(0)
    assert await rec.stop() is None


async def test_discard_e_close_liberam_o_microfone():
    rec = VoiceRecorder(mic_factory=FakeMic)
    rec.open()
    rec.start()
    await rec.discard()
    assert not rec.recording
    await rec.close()
    await rec.close()  # idempotente
    assert FakeMic.instances[-1].calls.count("stop") == 1
    assert not rec.is_open


async def test_microfone_ausente_vira_microphone_error():
    rec = VoiceRecorder(mic_factory=MagicMock(side_effect=OSError("sem dispositivo")))
    with pytest.raises(MicrophoneError):
        rec.open()
    with pytest.raises(MicrophoneError):
        rec.start()
