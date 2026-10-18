"""
Fluxo por utterance:
1. STT entrega texto via queue.
2. Pipeline dispara asyncio.Task para chamar LLM com streaming.
3. Um único stream de tokens é consumido e enviado simultaneamente ao
   display (terminal/janela X11) e ao TTS — sem chamar a API duas vezes.
4. Em paralelo, um flash-card/resumo do tópico é gerado (chamada LLM
   separada, não-streaming) e exibido no painel lateral do display assim
   que fica pronto — não bloqueia nem a fala nem a resposta principal.
5. TTS sintetiza e reproduz em thread daemon, sem bloquear novas utterances.
6. Próximo utterance pode iniciar enquanto o TTS ainda fala o anterior.

Foto (opcional, requer `camera`):
- A foto é tirada pela tecla de foto (hotkey) ou por gatilho de voz na própria
  fala ('tira uma foto', 'olha isso...'). Fica PENDENTE e é anexada à próxima
  pergunta; só é consumida quando a resposta chega (cancelar/erro preservam a
  foto) e expira após `photo_ttl_s`.
- Fala só com o gatilho ('tira uma foto'): captura, avisa por voz e espera a pergunta.

Controle:
- run_turn() é a variante awaitável de process_utterance(): o orquestrador
  aguarda o turno terminar (ou ser cancelado) antes de retomar o microfone.
- cancel_active() interrompe imediatamente o stream LLM (camada de rede),
  as tasks do pipeline e o áudio do TTS — acionada pela tecla de cancelamento.
"""

import asyncio
import logging
import re
import time
import unicodedata

from api.llm_client import LLMClient
from core import ui
from tts.speaker import TTSSpeaker
from vision.camera import CameraCapture, CameraError
from vision.image import CapturedImage

logger = logging.getLogger(__name__)

RESET_TRIGGERS = {"resetar", "reset", "nova sessão", "novo assunto", "recomeçar"}
_VALID_TEXT = re.compile(r"[a-zA-Z0-9á-úÁ-Ú]")

SENTENCE_ENDS = {".", "?", "!", "\n"}
_MIN_TTS_CHARS = 40

# Gatilhos de voz da câmera (comparados em minúsculas, sem acento nem pontuação).
_PHOTO_TRIGGER_RE = re.compile(
    r"\b(?:(?:tira|tire|tirar|bate|bata|bater)\s+(?:uma\s+)?foto"
    r"|(?:olha|olhe|veja)\s+(?:isso|isto|essa|esse|aqui)"
    r"|(?:usa|use|usar)\s+a\s+camera)\b"
)
# Sobras da fala que não formam uma pergunta (ex.: "tira uma foto por favor").
_PHOTO_FILLERS = frozenset(
    {"por", "favor", "pra", "mim", "agora", "entao", "ai", "ta", "ok", "tutor", "disso", "obrigado"}
)
_PHOTO_READY_MSG = "Pronto, tirei a foto! O que você quer saber sobre ela?"
_PHOTO_ERROR_MSG = "Não consegui usar a câmera agora."


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def parse_photo_request(utterance: str) -> tuple[bool, bool]:
    """Detecta pedido de foto por voz.

    Retorna (pediu_foto, tem_pergunta). `tem_pergunta` é False quando a fala é
    só o gatilho (ex.: "tira uma foto", "olha isso"): nesse caso o pipeline
    captura e espera a pergunta em vez de chamar o LLM.
    """
    plain = _normalize(utterance)
    match = _PHOTO_TRIGGER_RE.search(plain)
    if match is None:
        return False, True
    rest = f"{plain[: match.start()]} {plain[match.end() :]}".split()
    content = [w for w in rest if w not in _PHOTO_FILLERS]
    return True, len(content) >= 2


class HAIPipeline:
    """Orquestra STT -> LLM -> TTS -> Display de forma assíncrona e não-bloqueante.

    Parâmetros
    ----------
    llm_client : LLMClient
        Cliente LLM já configurado.
    tts : TTSSpeaker
        Speaker TTS já inicializado.
    display : MarkdownDisplay | None
        Janela X11 de exibição. Se fornecido, a resposta completa é
        renderizada via `display.show_response(markdown)` e, em paralelo, um
        flash-card do tópico é gerado via `llm_client.generate_flashcard()`
        e exibido via `display.show_flashcard(markdown)`. Se `None` (padrão),
        nenhuma geração de flash-card é feita — mantém o comportamento
        original quando não há display conectado.
    display_fn : callable | None
        Compatibilidade retroativa: função chamada com a resposta completa
        (texto) para atualizar um display simples. Deve ter assinatura
        (text: str) -> None. Pode ser usado junto com `display`.
    camera : CameraCapture | None
        Webcam para fotos. Se `None` (padrão), gatilhos de voz de foto são
        tratados como fala comum e nenhuma imagem é enviada ao LLM.
    photo_ttl_s : float
        Quanto tempo (s) uma foto pendente espera pela pergunta antes de expirar.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tts: TTSSpeaker,
        display=None,
        display_fn=None,
        camera: CameraCapture | None = None,
        photo_ttl_s: float = 120.0,
    ):
        self._llm = llm_client
        self._tts = tts
        self._display = display
        self._display_fn = display_fn
        self._camera = camera
        self._photo_ttl_s = photo_ttl_s
        self._pending_photo: CapturedImage | None = None
        self._active_tasks: set[asyncio.Task] = set()
        self._photo_tasks: set[asyncio.Task] = set()

    # Controle de turnos

    @property
    def busy(self) -> bool:
        """True se há pelo menos um turno em andamento."""
        return any(not t.done() for t in self._active_tasks)

    def process_utterance(self, utterance: str) -> None:
        """Dispara o turno fire-and-forget (API legada, usada pelos testes)."""
        if not _VALID_TEXT.search(utterance):
            logger.debug("Utterance ignorada (sem conteúdo válido): %r", utterance)
            return

        task = asyncio.create_task(
            self._handle_utterance(utterance), name=f"pipeline-{id(utterance)}"
        )
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    async def run_turn(self, utterance: str) -> None:
        """Processa um utterance aguardando o término (modo controlado).

        Levanta CancelledError se cancel_active() interromper o turno —
        o chamador decide como retomar (ex.: reabrir o microfone).
        """
        if not _VALID_TEXT.search(utterance):
            logger.debug("Utterance ignorada (sem conteúdo válido): %r", utterance)
            return

        task = asyncio.create_task(self._handle_utterance(utterance), name=f"turn-{id(utterance)}")

        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        await task

    def cancel_active(self) -> bool:
        """Cancela todo turno em andamento: stream LLM, tasks e áudio do TTS.

        Retorna True se algo estava em andamento. Idempotente.
        """
        had_work = False
        for task in list(self._active_tasks):
            if not task.done():
                task.cancel()
                had_work = True
        self._llm.cancel_stream()
        self._tts.stop_speaking()
        return had_work

    # Foto

    @property
    def camera_enabled(self) -> bool:
        return self._camera is not None

    @property
    def has_pending_photo(self) -> bool:
        return self._peek_photo() is not None

    def request_photo(self) -> None:
        """Dispara a captura sem aguardar (usada pela hotkey de foto)."""
        if self._camera is None:
            return
        if self.busy:
            ui.dim("Aguarde o tutor terminar de responder para tirar a foto.")
            return
        task = asyncio.create_task(self._photo_from_hotkey(), name="photo-hotkey")
        self._photo_tasks.add(task)
        task.add_done_callback(self._photo_tasks.discard)

    async def capture_photo(self) -> bool:
        """Tira uma foto e a deixa pendente para a próxima pergunta.

        Retorna False (já reportando o erro ao usuário) se não há câmera ou a
        captura falhou. Uma foto nova substitui a pendente anterior.
        """
        if self._camera is None:
            return False

        ui.photo_capturing()
        self._show_status("Capturando foto...")
        try:
            image = await self._camera.capture()
        except CameraError as exc:
            logger.warning("Falha ao capturar foto: %s", exc)
            ui.photo_failed(str(exc))
            self._show_status("Câmera indisponível")
            return False

        self._pending_photo = image
        ui.photo_ready(image.width, image.height, image.size_kb)
        self._show_status("Foto capturada — pode perguntar")
        return True

    def discard_photo(self) -> bool:
        """Descarta a foto pendente. Retorna True se havia uma."""
        had_photo = self._pending_photo is not None
        self._pending_photo = None
        if had_photo:
            ui.photo_discarded()
            self._show_status("Foto descartada")
        return had_photo

    def _peek_photo(self) -> CapturedImage | None:
        """Foto pendente ainda válida (expira após photo_ttl_s), sem consumi-la."""
        photo = self._pending_photo
        if photo is None:
            return None
        if time.monotonic() - photo.captured_at > self._photo_ttl_s:
            logger.info("Foto pendente expirou (%.0fs).", self._photo_ttl_s)
            self._pending_photo = None
            return None
        return photo

    async def _photo_from_hotkey(self) -> None:
        await self.capture_photo()
        ui.listening()

    def _show_status(self, text: str) -> None:
        if self._display is None:
            return
        try:
            self._display.show_status(text)
        except Exception:
            pass

    # Interno

    async def _handle_utterance(self, utterance: str) -> None:
        # Verifica trigger de reset
        if utterance.strip().lower() in RESET_TRIGGERS:
            self._llm.resetar_sessao()
            self._tts.stop_speaking()
            if self._display is not None:
                try:
                    self._display.clear()
                    self._display.show_status("Sessão reiniciada")
                except Exception as exc:
                    logger.warning("Erro ao limpar display: %s", exc)
            ui.success("\n[SESSÃO REINICIADA] Histórico apagado.")
            return

        # Foto: gatilho de voz na fala e/ou foto já pendente (tecla de foto).
        if self._camera is not None:
            asked, has_question = parse_photo_request(utterance)
            if asked:
                if not await self.capture_photo():
                    self._tts.speak(_PHOTO_ERROR_MSG)
                    return
                if not has_question:
                    self._tts.speak(_PHOTO_READY_MSG)
                    return
        photo = self._peek_photo()
        images = [photo] if photo is not None else []

        ui.thinking(utterance, photo=bool(images))
        self._show_status("Pensando...")

        # Resposta principal (streaming) e flash-card do tópico (não-stream) rodam concorrentemente: o flash-card não atrasa a fala nem o texto.
        if self._display is not None and hasattr(self._llm, "generate_flashcard"):
            answered, _ = await asyncio.gather(
                self._stream_response(utterance, images),
                self._generate_flashcard(utterance, images),
            )
        else:
            answered = await self._stream_response(utterance, images)

        # A foto só é consumida quando a resposta chegou: cancelar (levanta
        # CancelledError acima) ou falha de API mantêm a foto para a próxima tentativa.
        if answered and photo is not None and self._pending_photo is photo:
            self._pending_photo = None

    @staticmethod
    def _image_kwargs(images: list[CapturedImage]) -> dict:
        # Só passa `images` quando há foto: clientes/mocks sem suporte a imagem seguem válidos.
        return {"images": images} if images else {}

    async def _stream_response(self, utterance: str, images: list[CapturedImage]) -> bool:
        """Consome o stream do LLM. Retorna True se uma resposta completa foi obtida."""
        response_parts: list[str] = []
        tts_buffer = ""

        try:
            async for token in self._llm.send_stream(utterance, **self._image_kwargs(images)):
                response_parts.append(token)
                print(token, end="", flush=True)

                tts_buffer += token
                flush_idx = next((i for i, ch in enumerate(tts_buffer) if ch in SENTENCE_ENDS), -1)

                if flush_idx >= 0:
                    phrase = tts_buffer[: flush_idx + 1].strip()
                    tts_buffer = tts_buffer[flush_idx + 1 :]
                    if phrase:
                        self._tts.speak(phrase)
                        ui.speaking()
                elif len(tts_buffer) >= _MIN_TTS_CHARS:
                    comma_idx = tts_buffer.rfind(",")
                    if comma_idx > _MIN_TTS_CHARS // 2:
                        phrase = tts_buffer[: comma_idx + 1].strip()
                        tts_buffer = tts_buffer[comma_idx + 1 :]
                    else:
                        phrase = tts_buffer.strip()
                        tts_buffer = ""
                    if phrase:
                        self._tts.speak(phrase)
                        ui.speaking()

            # Flush do buffer restante
            if tts_buffer.strip():
                self._tts.speak(tts_buffer.strip())

        except asyncio.CancelledError:
            ui.cancelled_inline()
            raise

        except Exception as exc:
            logger.error("Erro no pipeline LLM→TTS: %s", exc)
            ui.error(f"\n[ERRO NA API] {exc}")
            return False

        full_response = "".join(response_parts).strip()
        print()

        if not full_response:
            return False

        if self._display is not None:
            try:
                self._display.show_response(full_response)
            except Exception as exc:
                logger.warning("Erro ao exibir resposta no display: %s", exc)

        if self._display_fn:
            try:
                self._display_fn(full_response)
            except Exception as exc:
                logger.warning("Erro no display_fn: %s", exc)

        return True

    async def _generate_flashcard(self, utterance: str, images: list[CapturedImage]) -> None:
        try:
            flashcard_md = await self._llm.generate_flashcard(
                utterance, **self._image_kwargs(images)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Erro ao gerar flashcard: %s", exc)
            return

        if flashcard_md and self._display is not None:
            try:
                self._display.show_flashcard(flashcard_md)
            except Exception as exc:
                logger.warning("Erro ao exibir flashcard: %s", exc)

    async def wait_pending(self) -> None:
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
