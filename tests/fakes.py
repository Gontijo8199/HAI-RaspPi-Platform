"""Dublês dos serviços (LLM, TTS, microfone, Whisper, câmera) para os testes."""

import asyncio

import numpy as np

from core.services import NullTTS
from stt.recorder import MicrophoneError
from vision.camera import CameraError
from vision.image import CapturedImage


class FakeLLM:
    def __init__(self, tokens=("Olá! ", "Tudo bem."), error=None):
        self.tokens = list(tokens)
        self.error = error
        self.gate: asyncio.Event | None = None
        self.sent: list[list] = []
        self.resets = 0
        self.cancels = 0

    def resetar_sessao(self):
        self.resets += 1

    def cancel_stream(self):
        self.cancels += 1

    async def send_parts_stream(self, parts):
        self.sent.append(list(parts))
        for i, token in enumerate(self.tokens):
            if i == 1 and self.gate is not None:
                await self.gate.wait()
            yield token
        if self.error is not None:
            raise self.error


class FakeTTS:
    def __init__(self):
        self.spoken: list[str] = []
        self.busy = False
        self.stops = 0

    def speak(self, text):
        self.spoken.append(text)

    def stop_speaking(self):
        self.stops += 1
        self.busy = False

    def is_busy(self):
        return self.busy


def _tone(seconds=0.5, rate=16000, amplitude=0.2) -> bytes:
    """PCM-16 de uma senoide de 440 Hz: "tem som" para o detector de silêncio."""
    t = np.arange(int(seconds * rate)) / rate
    return (np.sin(2 * np.pi * 440 * t) * amplitude * 32767).astype(np.int16).tobytes()


SPEECH_PCM = _tone()


class FakeRecorder:
    sample_rate = 16000

    def __init__(self, audio=None, fail_open=False):
        if audio is None:
            audio = SPEECH_PCM
        self.audio = audio
        self.fail_open = fail_open
        self.opened = 0
        self.closed = 0
        self.discarded = 0
        self.recording = False

    def open(self):
        if self.fail_open:
            raise MicrophoneError("Não consegui abrir o microfone.")
        self.opened += 1

    def start(self):
        self.recording = True

    async def stop(self):
        self.recording = False
        return self.audio

    async def discard(self):
        self.recording = False
        self.discarded += 1

    async def close(self):
        self.recording = False
        self.closed += 1


class FakeASR:
    def __init__(self, text="quanto é dois mais dois"):
        self.text = text
        self.gate: asyncio.Event | None = None
        self.calls = 0

    async def transcribe(self, audio, sample_rate):
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        return self.text


class Recorder:
    """Listener que só registra os eventos recebidos."""

    def __init__(self):
        self.events: list[tuple] = []

    def __getattr__(self, name):
        def record(*args):
            self.events.append((name, *args))

        return record

    def names(self):
        return [e[0] for e in self.events]

    def notices(self, kind=None):
        return [e[2] for e in self.events if e[0] == "notice" and (kind is None or e[1] == kind)]


def _image(n=1):
    """JPEG de verdade (40 × 30, cor por n): a interface decodifica as miniaturas."""
    import cv2

    frame = np.full((30, 40, 3), (40 * n % 256, 120, 200), dtype=np.uint8)
    ok, buffer = cv2.imencode(".jpg", frame)
    assert ok
    return CapturedImage(data=buffer.tobytes(), width=40, height=30)


class FakeCamera:
    def __init__(self, fail=False):
        self.fail = fail
        self.count = 0
        self.gate: asyncio.Event | None = None

    async def capture(self):
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise CameraError("câmera ocupada")
        self.count += 1
        return _image(self.count)


class FakeServices:
    """Mesma interface de core.services.Services usada pelo app e pelos módulos."""

    def __init__(self, llm_problem=None, camera=True, voice_output=True, keyboard=True):
        self.config_problems: list[str] = []
        self.settings: dict = {}
        self.on_screen_keyboard = keyboard
        self.llm = FakeLLM()
        self.llm_problem = llm_problem
        self.tts = FakeTTS() if voice_output else NullTTS()
        self.camera = FakeCamera() if camera else None
        self.asr = FakeASR()
        self.recorders: list[FakeRecorder] = []
        self.closed = 0
        self.preloads = 0

    @property
    def voice_output_available(self):
        return not isinstance(self.tts, NullTTS)

    async def get_asr(self):
        return self.asr

    def preload_asr(self):
        self.preloads += 1

    def make_recorder(self):
        recorder = FakeRecorder()
        self.recorders.append(recorder)
        return recorder

    def close(self):
        self.closed += 1
