"""
- A cada INTERIM_INTERVAL_MS de fala acumulada, dispara uma transcrição parcial em background para reduzir latência percebida.
- Quando o VAD detecta silêncio, dispara a transcrição FINAL.
- A transcrição parcial é CANCELADA antes de enfileirar a final, garantindo que apenas UMA transcrição por utterance chegue ao LLM.
- Se o parcial já tinha sido enfileirado antes do cancelamento, a fila é limpa antes de enfileirar a final.
"""

import asyncio
import logging

from .audio_stream import MicrophoneStream
from .vad import SileroVAD
from .whisper_engine import WhisperEngine

logger = logging.getLogger(__name__)

INTERIM_INTERVAL_MS = 1500


class WhisperStream:
    """Pipeline VAD → Whisper com interface assíncrona e streaming incremental.

    Parâmetros
    ----------
    language : str
        Código BCP-47 para o Whisper (ex.: 'pt', 'en').
    sample_rate : int
        Taxa de amostragem. Deve ser 16000.
    chunk_samples : int
        Amostras por frame do VAD. Deve ser 512.
    preroll_ms : int
        Janela do buffer de pre-roll em milissegundos.
    silence_ms : int
        Duração de silêncio contínuo (ms) que encerra uma gravação.
    vad_threshold : float
        Limiar de probabilidade de fala do Silero VAD (0–1).
    whisper_model : str
        Tamanho do modelo Faster-Whisper. 'small' recomendado para Pi 5.
    whisper_device : str
        'cpu' ou 'cuda'.
    whisper_compute_type : str
        Quantização do Whisper. Use sempre 'int8' na CPU.
    device_index : int | None
        Índice do dispositivo PyAudio. None usa o padrão do sistema.
    interim_interval_ms : int
        Intervalo de áudio acumulado (ms) para disparar transcrição parcial.
        0 = desativa streaming parcial.
    """

    SAMPLE_RATE = 16000
    CHUNK_SAMPLES = 512  # 32 ms @ 16 kHz, exigido pelo Silero VAD

    def __init__(
        self,
        language: str = "pt",
        sample_rate: int = 16000,
        chunk_samples: int = 512,
        preroll_ms: int = 500,
        silence_ms: int = 700,
        vad_threshold: float = 0.5,
        whisper_model: str = "small",
        whisper_device: str = "cpu",
        whisper_compute_type: str = "int8",
        device_index: int | None = None,
        interim_interval_ms: int = INTERIM_INTERVAL_MS,
    ):
        if sample_rate != 16000:
            raise ValueError("sample_rate deve ser 16000 (exigência do Silero VAD).")
        if chunk_samples != 512:
            raise ValueError("chunk_samples deve ser 512 (exigência do Silero VAD).")

        self._sample_rate = sample_rate

        frame_ms = (chunk_samples / sample_rate) * 1000
        self._silence_frames = max(1, int(silence_ms / frame_ms))
        self._interim_frames = (
            max(1, int(interim_interval_ms / frame_ms)) if interim_interval_ms > 0 else 0
        )

        self._mic = MicrophoneStream(
            sample_rate=sample_rate,
            chunk_samples=chunk_samples,
            preroll_ms=preroll_ms,
            device_index=device_index,
        )
        self._vad = SileroVAD(threshold=vad_threshold, sample_rate=sample_rate)
        self._asr = WhisperEngine(
            model_size=whisper_model,
            device=whisper_device,
            compute_type=whisper_compute_type,
            language=language,
        )

        self._utterance_queue: asyncio.Queue[str] = asyncio.Queue()
        self._is_running = False
        self._pipeline_task: asyncio.Task | None = None

        # Task da transcrição parcial em andamento.
        # Cancelada quando a transcrição final está pronta — garante que
        # apenas a transcrição final chega ao LLM.
        self._interim_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._is_running = True
        loop = asyncio.get_running_loop()
        self._mic.start(loop)
        self._pipeline_task = asyncio.create_task(self._pipeline_loop(), name="vad-pipeline")
        self._pipeline_task.add_done_callback(self._task_error_handler)

    async def get_utterance(self) -> str:
        return await self._utterance_queue.get()

    def stop(self) -> None:
        self._is_running = False
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
        self._mic.stop()
        logger.info("WhisperStream encerrado.")

    # ------------------------------------------------------------------
    # Loop interno
    # ------------------------------------------------------------------

    async def _pipeline_loop(self) -> None:
        recording: list[bytes] = []
        silent_frames = 0
        speech_frames = 0
        is_recording = False

        logger.info("Pipeline VAD iniciado. Aguardando fala...")
        print("Ouvindo... (fale qualquer coisa)")

        while self._is_running:
            try:
                chunk = await self._mic.read_chunk()
            except Exception as exc:
                logger.error("Erro ao ler chunk do microfone: %s", exc)
                break

            speech, prob = self._vad.is_speech(chunk)

            if speech:
                if not is_recording:
                    logger.debug("Onset de fala detectado (prob=%.2f)", prob)
                    self._vad.reset_state()
                    preroll = self._mic.get_preroll()
                    recording = [preroll, chunk] if preroll else [chunk]
                    is_recording = True
                    silent_frames = 0
                    speech_frames = 1
                    self._interim_task = None
                    print("\n[GRAVANDO...]")
                else:
                    recording.append(chunk)
                    silent_frames = 0
                    speech_frames += 1

                    # Dispara parcial apenas se streaming está ativado e
                    # não há outro parcial em andamento
                    if (
                        self._interim_frames > 0
                        and speech_frames >= self._interim_frames
                        and (self._interim_task is None or self._interim_task.done())
                    ):
                        audio_snapshot = b"".join(recording)
                        self._interim_task = asyncio.create_task(
                            self._transcribe_interim(audio_snapshot),
                            name="transcribe-interim",
                        )
                        speech_frames = 0

            elif is_recording:
                recording.append(chunk)
                silent_frames += 1

                if silent_frames >= self._silence_frames:
                    is_recording = False
                    audio_bytes = b"".join(recording)
                    recording = []
                    silent_frames = 0
                    speech_frames = 0
                    self._mic.clear_preroll()

                    # Cancela o parcial antes de disparar o final
                    if self._interim_task and not self._interim_task.done():
                        self._interim_task.cancel()
                        logger.debug("Transcrição parcial cancelada — final em andamento.")

                    asyncio.create_task(
                        self._transcribe_final(audio_bytes),
                        name="transcribe-final",
                    )
                    self._interim_task = None

    async def _transcribe_interim(self, audio_bytes: bytes) -> None:
        """Transcrição parcial — usada apenas para pré-aquecer o modelo.
        Não enfileira nada; o resultado é descartado se a final cancelar esta task.
        """
        print("[TRANSCREVENDO PARCIAL...]")
        try:
            await self._asr.transcribe(audio_bytes, self._sample_rate)
            # Resultado descartado intencionalmente — só a final vai para a fila
            logger.debug("Parcial concluído (descartado, aguardando final).")
        except asyncio.CancelledError:
            logger.debug("Parcial cancelado pela transcrição final.")
        except Exception as exc:
            logger.warning("Erro na transcrição parcial: %s", exc)

    async def _transcribe_final(self, audio_bytes: bytes) -> None:
        """Transcrição final — única que vai para a fila do pipeline."""
        print("[PROCESSANDO ÁUDIO...]")
        try:
            text = await self._asr.transcribe(audio_bytes, self._sample_rate)
        except Exception as exc:
            logger.error("Erro na transcrição Whisper: %s", exc)
            return

        if text and len(text) > 2:
            logger.info("Transcrição: %s", text)
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
