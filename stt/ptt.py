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

    Controles:
    - Enter inicia/encerra a gravação.
    - A tecla de cancelamento (padrão Espaço, configurável via
      [ux] cancel_key) durante a gravação descarta o áudio e volta a aguardar.
    - Enter enquanto o tutor responde é ignorado (mic mutado); a tecla de
      cancelamento aborta o pedido — tratado pelo orquestrador via pipeline.

    Parâmetros
    ----------
    hotkeys : HotkeyListener | None
        Listener compartilhado de teclas. Quando fornecido, as teclas chegam
        por ele (stdin fica em modo cbreak, gerido por ele). Quando None,
        cai no comportamento legado de ler linhas com sys.stdin.readline —
        sem suporte a cancelamento, mas mantém compatibilidade com os testes.
    cancel_key : str
        Token canônico da tecla de cancelamento (saída de core.hotkeys.parse_key).
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
        hotkeys=None,
        cancel_key: str = "space",
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
        self._hotkeys = hotkeys if (hotkeys is not None and hotkeys.available) else None
        self._cancel_key = cancel_key

        self._utterance_queue: asyncio.Queue[str] = asyncio.Queue()
        self._is_running = False
        self._pipeline_task: asyncio.Task | None = None
        self._muted = False

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

    def pause(self) -> None:
        """Interrompe a captura durante o turno do tutor."""
        self._muted = True
        self._mic.pause()

    def resume(self) -> None:
        """Retoma a captura com buffers limpos."""
        self._muted = False
        self._mic.resume()

    async def _ptt_loop(self) -> None:
        from core.hotkeys import pretty_key

        tecla = pretty_key(self._cancel_key)
        print(
            "Modo PTT ativo. Pressione Enter para começar a gravar; "
            f"Enter novamente para enviar; {tecla} descarta a gravação."
        )

        while self._is_running:
            action = await self._wait_action("Pressione Enter para gravar...")
            if not self._is_running:
                break

            if self._muted:
                print(
                    f"[O tutor está respondendo — aguarde ou pressione {tecla} para cancelar.]"
                )
                continue

            self._mic.drain_queue()
            print(
                f"[GRAVANDO... pressione Enter para encerrar, {tecla} para descartar]"
            )
            recording: list[bytes] = []

            stop_event = asyncio.Event()
            producer = asyncio.create_task(
                self._coletar_chunks(recording, stop_event), name="ptt-coletar"
            )

            action = await self._wait_action()
            stop_event.set()
            await producer

            # Tecla de cancelamento durante a gravação: descarta e volta a aguardar.
            if action == "cancel":
                print("[GRAVAÇÃO DESCARTADA]")
                continue
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

    async def _wait_action(self, prompt: str = "") -> str:
        """Espera 'enter' ou a tecla de cancelamento. Outras teclas são ignoradas.

        Sem HotkeyListener (ex.: testes), usa readline e só retorna 'enter'.
        """
        if prompt:
            print(prompt, end="", flush=True)

        if self._hotkeys is None:
            await asyncio.to_thread(sys.stdin.readline)
            return "enter"

        while True:
            key = await self._hotkeys.get_key()
            if key == "enter":
                return "enter"
            if key == self._cancel_key:
                return "cancel"
            # teclas soltas durante a gravação são ignoradas

    async def _transcribe_and_enqueue(self, audio_bytes: bytes) -> None:
        print("[PROCESSANDO ÁUDIO...]")
        try:
            text = await self._asr.transcribe(audio_bytes, self._sample_rate)
        except Exception as exc:
            logger.error("Erro na transcrição Whisper: %s", exc)
            return

        if self._muted:
            logger.info("Transcrição PTT descartada: captura pausada.")
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
