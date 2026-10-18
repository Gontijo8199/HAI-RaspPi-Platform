"""Dublês dos serviços (LLM, TTS, microfone, Whisper, câmera) para os testes."""

import asyncio

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


class FakeRecorder:
    sample_rate = 16000

    def __init__(self, audio=b"\x00\x01" * 8000, fail_open=False):
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
    return CapturedImage(data=b"\xff\xd8" + bytes([n]), width=10, height=10)


class FakeCamera:
    def __init__(self, fail=False):
        self.fail = fail
        self.count = 0

    async def capture(self):
        if self.fail:
            raise CameraError("câmera ocupada")
        self.count += 1
        return _image(self.count)


class FakeServices:
    """Mesma interface de core.services.Services usada pelo app e pelos módulos."""

    def __init__(self, llm_problem=None, camera=True, voice_output=True):
        self.config_problems: list[str] = []
        self.llm = FakeLLM()
        self.llm_problem = llm_problem
        self.tts = FakeTTS() if voice_output else NullTTS()
        self.camera = FakeCamera() if camera else None
        self.asr = FakeASR()
        self.recorders: list[FakeRecorder] = []
        self.closed = 0

    @property
    def voice_output_available(self):
        return not isinstance(self.tts, NullTTS)

    async def get_asr(self):
        return self.asr

    def make_recorder(self):
        recorder = FakeRecorder()
        self.recorders.append(recorder)
        return recorder

    def close(self):
        self.closed += 1
