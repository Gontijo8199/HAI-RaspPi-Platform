# Import tardio: a interface gráfica só usa stt.recorder/stt.whisper_engine e não
# precisa carregar o torch (Silero VAD) que stt.capture importa.
__all__ = ["WhisperStream", "PttStream"]


def __getattr__(name: str):
    if name == "WhisperStream":
        from .capture import WhisperStream

        return WhisperStream
    if name == "PttStream":
        from .ptt import PttStream

        return PttStream
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
