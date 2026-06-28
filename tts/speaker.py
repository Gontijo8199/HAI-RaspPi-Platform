"""
Backends suportados:
- 'piper'   - voz neural offline, qualidade natural (RECOMENDADO)
- 'espeak'  - robótico mas leve, fallback
- 'pyttsx3' - wrapper do espeak via Python

Design:
- Thread daemon consome uma Queue de frases sequencialmente.
- speak() enfileira e retorna imediatamente (fire-and-forget).
- speak_stream() agrupa tokens em frases e inicia fala antes da resposta terminar.
- stop_speaking() interrompe síntese atual e limpa fila pendente.
"""

import logging
import queue
import subprocess
import threading
from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

_STOP = object()  # encerra o worker
_INTERRUPT = object()  # interrompe utterance atual e limpa fila


class TTSSpeaker:
    """TTS não-bloqueante com fila de utterances.

    Parâmetros
    ----------
    backend : str
        'piper' (recomendado), 'espeak' ou 'pyttsx3'.
    piper_bin : str
        Caminho para o executável do Piper.
    piper_model : str
        Caminho para o arquivo .onnx da voz Piper.
    rate : int
        Velocidade de fala (palavras por minuto) — usado pelo espeak/pyttsx3.
    volume : float
        Volume entre 0.0 e 1.0 — usado pelo pyttsx3.
    lang : str
        Código de idioma para espeak-ng (ex.: 'pt-br').
    """

    def __init__(
        self,
        backend: str = "piper",
        piper_bin: str = "/home/rafa/piper/piper/piper",
        piper_model: str = "/home/rafa/piper/voices/pt_BR-faber-medium.onnx",
        rate: int = 160,
        volume: float = 0.9,
        lang: str = "pt-br",
    ):
        self._backend = backend
        self._piper_bin = piper_bin
        self._piper_model = piper_model
        self._rate = rate
        self._volume = volume
        self._lang = lang

        # Processo Piper em andamento (para interrupção)
        self._current_proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()

        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="tts-worker")
        self._thread.start()
        logger.info("TTSSpeaker iniciado (backend=%s).", backend)

    def speak(self, text: str) -> None:
        if text.strip():
            self._queue.put(text)

    async def speak_stream(self, token_stream: AsyncIterator[str]) -> None:
        buffer = ""
        SENTENCE_ENDS = {".", "?", "!", "\n"}
        MIN_CHARS = 40

        async for token in token_stream:
            buffer += token

            flush_idx = -1
            for i, ch in enumerate(buffer):
                if ch in SENTENCE_ENDS:
                    flush_idx = i
                    break

            if flush_idx >= 0:
                phrase = buffer[: flush_idx + 1].strip()
                buffer = buffer[flush_idx + 1 :]
                if phrase:
                    self.speak(phrase)
            elif len(buffer) >= MIN_CHARS:
                comma_idx = buffer.rfind(",")
                if comma_idx > MIN_CHARS // 2:
                    phrase = buffer[: comma_idx + 1].strip()
                    buffer = buffer[comma_idx + 1 :]
                else:
                    phrase = buffer.strip()
                    buffer = ""
                if phrase:
                    self.speak(phrase)

        if buffer.strip():
            self.speak(buffer.strip())

    def stop_speaking(self) -> None:
        # Esvazia fila
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        # Mata processo em andamento (Piper ou espeak)
        with self._proc_lock:
            if self._current_proc and self._current_proc.poll() is None:
                self._current_proc.terminate()
        self._queue.put(_INTERRUPT)

    def shutdown(self) -> None:
        self._queue.put(_STOP)
        self._thread.join(timeout=3.0)
        logger.info("TTSSpeaker encerrado.")

    def _worker(self) -> None:
        if self._backend == "piper":
            self._worker_piper()
        elif self._backend == "espeak":
            self._worker_espeak()
        elif self._backend == "pyttsx3":
            self._worker_pyttsx3()
        else:
            logger.error(
                "Backend TTS desconhecido: %s. Use 'piper', 'espeak' ou 'pyttsx3'.", self._backend
            )

    def _worker_piper(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            if item is _INTERRUPT:
                continue  # processo já foi terminado em stop_speaking()

            try:
                # Piper gera PCM raw; aplay reproduz direto
                piper_cmd = [
                    self._piper_bin,
                    "--model",
                    self._piper_model,
                    "--output_raw",
                ]
                aplay_cmd = [
                    "aplay",
                    "-r",
                    "22050",
                    "-f",
                    "S16_LE",
                    "-c",
                    "1",
                    "-q",  # silencia mensagens do aplay
                ]

                with self._proc_lock:
                    piper_proc = subprocess.Popen(
                        piper_cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                    )
                    aplay_proc = subprocess.Popen(
                        aplay_cmd,
                        stdin=piper_proc.stdout,
                        stderr=subprocess.DEVNULL,
                    )
                    piper_proc.stdout.close()
                    self._current_proc = aplay_proc

                # Envia texto para o Piper
                piper_proc.stdin.write(item.encode("utf-8"))
                piper_proc.stdin.close()

                piper_proc.wait(timeout=30)
                aplay_proc.wait(timeout=30)

            except FileNotFoundError:
                logger.error(
                    "Piper não encontrado em '%s'. "
                    "Verifique o caminho em settings.toml [tts] piper_bin.",
                    self._piper_bin,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Piper timeout para: %r", item[:50])
                with self._proc_lock:
                    if self._current_proc:
                        self._current_proc.terminate()
            except Exception as exc:
                logger.warning("Erro TTS Piper: %s", exc)
            finally:
                with self._proc_lock:
                    self._current_proc = None

    def _worker_espeak(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            if item is _INTERRUPT:
                continue
            try:
                with self._proc_lock:
                    proc = subprocess.Popen(
                        [
                            "espeak-ng",
                            "-v",
                            self._lang,
                            "-s",
                            str(self._rate),
                            "-a",
                            str(int(self._volume * 200)),
                            item,
                        ],
                        stderr=subprocess.DEVNULL,
                    )
                    self._current_proc = proc
                proc.wait(timeout=30)
            except FileNotFoundError:
                logger.error("espeak-ng não encontrado: sudo apt install espeak-ng")
            except subprocess.TimeoutExpired:
                logger.warning("espeak-ng timeout para: %r", item[:50])
                proc.terminate()
            except Exception as exc:
                logger.warning("Erro TTS espeak: %s", exc)
            finally:
                with self._proc_lock:
                    self._current_proc = None

    def _worker_pyttsx3(self) -> None:
        try:
            import pyttsx3  # type: ignore
        except ImportError:
            logger.error("pyttsx3 não instalado. pip install pyttsx3. Caindo para espeak.")
            self._backend = "espeak"
            self._worker_espeak()
            return

        engine = pyttsx3.init()
        engine.setProperty("rate", self._rate)
        engine.setProperty("volume", self._volume)

        voices = engine.getProperty("voices")
        for v in voices:
            lang = v.languages[0] if v.languages else ""
            if "pt" in lang.lower() or "portuguese" in v.name.lower() or "brasil" in v.name.lower():
                engine.setProperty("voice", v.id)
                logger.info("Voz pyttsx3 selecionada: %s", v.name)
                break

        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            if item is _INTERRUPT:
                engine.stop()
                continue
            try:
                engine.say(item)
                engine.runAndWait()
            except Exception as exc:
                logger.warning("Erro TTS pyttsx3: %s", exc)
