import asyncio
import logging

import pyaudio

logger = logging.getLogger(__name__)


class MicrophoneStream:
    """Stream de microfone que alimenta uma asyncio.Queue com chunks PCM-16 mono.

    O callback do PyAudio roda numa thread C do PortAudio e usa
    call_soon_threadsafe para entregar os chunks sem bloquear o event loop.

    Parâmetros
    ----------
    sample_rate : int
        Taxa de amostragem em Hz (16000 é o que o Whisper espera).
    chunk_samples : int
        Amostras por chunk entregue à fila.
    device_index : int | None
        Índice do dispositivo PyAudio. None usa o padrão do sistema.
    """

    FORMAT = pyaudio.paInt16
    CHANNELS = 1

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_samples: int = 512,
        device_index: int | None = None,
    ):
        self.sample_rate = sample_rate
        self.chunk_samples = chunk_samples
        self.device_index = device_index

        self._audio = pyaudio.PyAudio()
        self._stream: pyaudio.Stream | None = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._running = True
        self._stream = self._audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_samples,
            input_device_index=self.device_index,
            stream_callback=self._callback,
        )
        self._stream.start_stream()
        logger.info(
            "Microfone aberto - %d Hz, chunk=%d amostras (%.0f ms)",
            self.sample_rate,
            self.chunk_samples,
            self.chunk_samples / self.sample_rate * 1000,
        )

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
        self._audio.terminate()

    def pause(self) -> None:
        """Interrompe a captura no nível do PortAudio (o callback para de rodar).

        Nenhum chunk novo chega à fila e os pendentes são descartados, então
        nada do que for dito durante a pausa é capturado ou retido. Idempotente.
        """
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop_stream()
            except Exception as exc:
                logger.warning("Erro ao pausar stream: %s", exc)
        self.drain_queue()
        logger.debug("Microfone pausado.")

    def resume(self) -> None:
        """Retoma a captura com a fila limpa (sem áudio residual da pausa)."""
        self.drain_queue()
        self._running = True
        if self._stream is not None:
            try:
                self._stream.start_stream()
            except Exception as exc:
                logger.error("Erro ao retomar stream: %s", exc)
        logger.debug("Microfone retomado.")

    async def read_chunk(self) -> bytes:
        return await self._queue.get()

    def drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _callback(
        self,
        in_data: bytes,
        frame_count: int,
        time_info: dict,
        status_flags: int,
    ):
        if self._running and self._loop is not None:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, in_data)
        return (None, pyaudio.paContinue)
