import asyncio
import logging
import sys

from .audio_stream import MicrophoneStream
from .whisper_engine import WhisperEngine

logger = logging.getLogger(__name__)


class PttStream:
    """Captura de voz ativada por Enter no terminal (Press-to-Talk).

    Interface pública idêntica à de WhisperStream; substituível sem
    alterações em main.py::

        stt = PttStream(language="pt")
        await stt.start()
        utterance = await stt.get_utterance()
        stt.stop()

    Parâmetros
    ----------
    language : str
        Código BCP-47 para o Whisper (ex.: 'pt', 'en').
    sample_rate : int
        Taxa de amostragem em Hz.
    chunk_samples : int
        Amostras por chunk do PyAudio.
    whisper_model : str
        Tamanho do modelo Faster-Whisper. 'small' recomendado para Pi 5.
    whisper_device : str
        'cpu' ou 'cuda'.
    whisper_compute_type : str
        Quantização do Whisper. Use sempre 'int8' na CPU.
    device_index : int | None
        Índice do dispositivo PyAudio. None usa o padrão do sistema.
    """

    def __init__(
        self,
        language: str = "pt",
        sample_rate: int = 16000,
        chunk_samples: int = 512,
        whisper_model: str = "small",
        whisper_device: str = "cpu",
        whisper_compute_type: str = "int8",
        device_index: int | None = None,
    ):
        self._sample_rate = sample_rate

        self._mic = MicrophoneStream(
            sample_rate=sample_rate,
            chunk_samples=chunk_samples,
            preroll_ms=0,
            device_index=device_index,
        )
        self._asr = WhisperEngine(
            model_size=whisper_model,
            device=whisper_device,
            compute_type=whisper_compute_type,
            language=language,
        )

        self._utterance_queue: asyncio.Queue[str] = asyncio.Queue()
        self._is_running = False
        self._pipeline_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._is_running = True
        loop = asyncio.get_running_loop()
        self._mic.start(loop)
        self._pipeline_task = asyncio.create_task(self._ptt_loop(), name="ptt-pipeline")
        self._pipeline_task.add_done_callback(self._task_error_handler)

    async def get_utterance(self) -> str:
        return await self._utterance_queue.get()

    def stop(self) -> None:
        self._is_running = False
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
        self._mic.stop()
        logger.info("PttStream encerrado.")

    async def _ptt_loop(self) -> None:
        print("Modo PTT ativo. Pressione Enter para começar a gravar; Enter novamente para enviar.")

        while self._is_running:
            await self._aguardar_enter("Pressione Enter para gravar...")
            if not self._is_running:
                break

            print("[GRAVANDO... pressione Enter para encerrar]")
            recording: list[bytes] = []

            stop_event = asyncio.Event()
            producer = asyncio.create_task(
                self._coletar_chunks(recording, stop_event), name="ptt-coletar"
            )

            await self._aguardar_enter()
            stop_event.set()
            await producer

            if not recording:
                continue

            audio_bytes = b"".join(recording)
            asyncio.create_task(self._transcribe_and_enqueue(audio_bytes), name="ptt-transcribe")

    async def _coletar_chunks(self, recording: list[bytes], stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                chunk = await asyncio.wait_for(self._mic.read_chunk(), timeout=0.1)
                recording.append(chunk)
            except TimeoutError:
                continue
            except Exception as exc:
                logger.error("Erro ao coletar chunk PTT: %s", exc)
                break

    async def _aguardar_enter(self, prompt: str = "") -> None:
        if prompt:
            print(prompt, end="", flush=True)
        await asyncio.to_thread(sys.stdin.readline)

    async def _transcribe_and_enqueue(self, audio_bytes: bytes) -> None:
        print("[PROCESSANDO ÁUDIO...]")
        try:
            text = await self._asr.transcribe(audio_bytes, self._sample_rate)
        except Exception as exc:
            logger.error("Erro na transcrição Whisper: %s", exc)
            return

        if text and len(text) > 2:
            logger.info("Transcrição PTT: %s", text)
            await self._utterance_queue.put(text)
        else:
            logger.debug("Transcrição vazia ou muito curta, descartando.")
            print("[ÁUDIO DESCARTADO — sem conteúdo detectável]")

    @staticmethod
    def _task_error_handler(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.critical(
                "Task '%s' terminou com exceção: %s", task.get_name(), exc, exc_info=exc
            )
