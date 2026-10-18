"""
Lógica do módulo "Conversar com a IA" — sem nenhuma dependência de Tk.

Fluxo (o mesmo da POC conversar-llm.html, ligado aos serviços reais):
1. O aluno monta a pergunta como uma lista ordenada de blocos: texto digitado,
   fala transcrita (segurar para falar → Whisper local) e fotos da webcam.
   Blocos podem ser editados, removidos ou inseridos entre outros.
2. Enviar manda TODOS os blocos, na ordem, numa única requisição multimodal
   (LLMClient.send_parts_stream) para o chat da sessão atual.
3. Os tokens vão para a tela conforme chegam e, frase a frase, para o TTS.
4. Falha/cancelamento devolve os blocos ao rascunho para tentar de novo.

Uma atividade por vez (Activity): gravar, transcrever, fotografar e enviar não
se sobrepõem, o que impede envios duplicados e gravações simultâneas.

Isolamento e privacidade:
- Nada é gravado em disco. Histórico, rascunho e fotos vivem só na memória.
- new_conversation() e stop() (saída do módulo) recriam a sessão do LLM e
  apagam mensagens, rascunho e fotos.
- Toda tarefa assíncrona carrega a "época" em que nasceu; stop() e
  new_conversation() avançam a época e cancelam as tarefas, então um resultado
  atrasado (transcrição, foto, token do LLM) nunca chega a uma tela encerrada
  ou a uma conversa nova. Depois de stop() o listener é solto.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import itertools
import logging
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, Protocol

from api.llm_client import LLMError, describe_error
from core.services import SpeechUnavailable
from stt.recorder import MicrophoneError
from tts.chunker import SentenceChunker
from vision.camera import CameraError
from vision.image import CapturedImage

logger = logging.getLogger(__name__)

_SPEAKING_POLL_S = 0.1
_NO_SPEECH = "(não entendi o áudio — tente falar mais perto do microfone)"


class Activity(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    CAPTURING = "capturing"
    THINKING = "thinking"  # pedido enviado, aguardando o primeiro token
    RESPONDING = "responding"  # tokens chegando
    SPEAKING = "speaking"  # texto completo, TTS ainda falando


class VoiceStatus(enum.Enum):
    LOADING = "loading"
    READY = "ready"
    UNAVAILABLE = "unavailable"


@dataclass
class DraftBlock:
    """Um pedaço da pergunta em composição."""

    id: int
    kind: str  # "text" | "photo"
    text: str = ""
    image: CapturedImage | None = None
    label: str = ""  # "foto 1", ...
    pending: str | None = None  # "gravando...", "transcrevendo..." (bloco ainda sem texto)

    @property
    def is_empty(self) -> bool:
        return self.kind == "text" and (self.pending is not None or not self.text.strip())


@dataclass
class ChatMessage:
    id: int
    role: str  # "user" | "ai"
    blocks: list[DraftBlock] = field(default_factory=list)  # mensagem do aluno
    text: str = ""  # resposta da IA (Markdown)
    status: str = "done"  # "thinking" | "streaming" | "done" | "error" | "cancelled"
    error: str = ""


class ChatListener(Protocol):
    """O que a tela precisa implementar (chamado sempre no event loop)."""

    def activity_changed(self, activity: Activity) -> None: ...
    def voice_status_changed(self, status: VoiceStatus, reason: str) -> None: ...
    def draft_changed(self, blocks: list[DraftBlock], focus_id: int | None) -> None: ...
    def message_added(self, message: ChatMessage) -> None: ...
    def message_updated(self, message: ChatMessage) -> None: ...
    def conversation_cleared(self) -> None: ...
    def notice(self, kind: str, text: str) -> None: ...  # kind: "info" | "error"


class ChatSession:
    """Estado e operações de uma conversa.

    Parâmetros
    ----------
    llm : LLMClient
        Cliente compartilhado; a sessão do chat é recriada a cada conversa.
    tts : TTSSpeaker | NullTTS
        Fala as respostas frase a frase (se voice_output estiver ligado).
    camera : CameraCapture | None
        Webcam; None desativa o botão de foto.
    recorder : VoiceRecorder | None
        Microfone do módulo; None desativa a entrada por voz.
    get_asr : coroutine function | None
        Devolve o WhisperEngine compartilhado (carregado sob demanda).
    """

    def __init__(self, llm, tts, camera=None, recorder=None, get_asr=None):
        self._llm = llm
        self._tts = tts
        self._camera = camera
        self._recorder = recorder
        self._get_asr = get_asr

        self.listener: ChatListener | None = None
        self.activity = Activity.IDLE
        self.voice_status = VoiceStatus.UNAVAILABLE
        self.voice_reason = "Entrada por voz indisponível."
        self.voice_output = True
        self.draft: list[DraftBlock] = []
        self.messages: list[ChatMessage] = []

        self._ids = itertools.count(1)
        self._photo_count = 0
        self._epoch = 0
        self._task: asyncio.Task | None = None  # atividade em andamento
        self._background: set[asyncio.Task] = set()  # preparo da voz
        self._recording_block: DraftBlock | None = None
        self._sending: list[DraftBlock] = []  # blocos do envio em andamento
        self._started = False

    # ------------------------------------------------------------------ ciclo de vida

    @property
    def camera_available(self) -> bool:
        return self._camera is not None

    @property
    def busy(self) -> bool:
        return self.activity not in (Activity.IDLE, Activity.SPEAKING)

    async def start(self) -> None:
        """Conversa nova + microfone aberto (pausado) + Whisper em preparo."""
        self._started = True
        self._epoch += 1
        self._llm.resetar_sessao()
        if self._recorder is None or self._get_asr is None:
            self._set_voice(VoiceStatus.UNAVAILABLE, "Entrada por voz indisponível.")
            return
        try:
            self._recorder.open()
        except MicrophoneError as exc:
            self._set_voice(VoiceStatus.UNAVAILABLE, str(exc))
            return
        self._set_voice(VoiceStatus.LOADING, "Preparando o reconhecimento de voz...")
        self._spawn_background(self._prepare_voice())

    async def stop(self) -> None:
        """Saída do módulo: cancela tudo, fecha o microfone e apaga a conversa."""
        if not self._started:
            return
        self._started = False
        self.listener = None
        await self._abort_everything()
        for task in list(self._background):
            task.cancel()
        await asyncio.gather(*self._background, return_exceptions=True)
        self._background.clear()
        if self._recorder is not None:
            await self._recorder.close()
        self._llm.resetar_sessao()
        self._wipe()
        self.activity = Activity.IDLE

    async def new_conversation(self) -> None:
        """Esquece a conversa atual (histórico do LLM, mensagens, rascunho, fotos)."""
        await self._abort_everything()
        self._llm.resetar_sessao()
        self._wipe()
        self._set_activity(Activity.IDLE)
        self._emit("conversation_cleared")
        self._emit("draft_changed", self.draft, None)
        self._emit("notice", "info", "Conversa nova! A anterior não foi guardada (privacidade).")

    # ------------------------------------------------------------------ rascunho

    def add_text_block(self, index: int | None = None) -> DraftBlock:
        block = DraftBlock(id=next(self._ids), kind="text")
        if index is None or not 0 <= index <= len(self.draft):
            self.draft.append(block)
        else:
            self.draft.insert(index, block)
        self._emit("draft_changed", self.draft, block.id)
        return block

    def set_text(self, block_id: int, text: str) -> None:
        """Texto editado pelo aluno (não redesenha o rascunho)."""
        block = self._find(block_id)
        if block is not None and block.kind == "text" and block.pending is None:
            block.text = text

    def remove_block(self, block_id: int) -> None:
        block = self._find(block_id)
        if block is None:
            return
        if block is self._recording_block and self.activity in (
            Activity.RECORDING,
            Activity.TRANSCRIBING,
        ):
            # Remover o bloco que está sendo gravado/transcrito cancela a operação.
            self.cancel()
            return
        self.draft.remove(block)
        self._emit("draft_changed", self.draft, None)

    # ------------------------------------------------------------------ voz

    def begin_recording(self) -> bool:
        """Botão "segurar para falar" pressionado. Retorna True se começou a gravar."""
        if self.voice_status is not VoiceStatus.READY:
            self._emit("notice", "error", self.voice_reason)
            return False
        if self.busy:
            return False
        self._stop_speaking()
        try:
            self._recorder.start()
        except MicrophoneError as exc:
            self._emit("notice", "error", str(exc))
            return False
        block = DraftBlock(id=next(self._ids), kind="text", pending="gravando...")
        self._recording_block = block
        self.draft.append(block)
        self._set_activity(Activity.RECORDING)
        self._emit("draft_changed", self.draft, None)
        return True

    def finish_recording(self) -> None:
        """Botão solto: encerra a gravação e transcreve."""
        if self.activity is not Activity.RECORDING:
            return
        self._run_activity(self._transcribe(self._epoch))

    async def _transcribe(self, epoch: int) -> None:
        block = self._recording_block
        try:
            audio = await self._recorder.stop()
            if audio is None:
                self._drop_block(block)
                self._emit("notice", "info", "Gravação muito curta: segure o botão enquanto fala.")
                return
            self._set_activity(Activity.TRANSCRIBING)
            self._set_pending(block, "transcrevendo...")
            asr = await self._get_asr()
            text = await asr.transcribe(audio, self._recorder.sample_rate)
        except asyncio.CancelledError:
            if epoch == self._epoch:
                self._drop_block(block)
            raise
        except SpeechUnavailable as exc:
            self._drop_block(block)
            self._set_voice(VoiceStatus.UNAVAILABLE, str(exc))
            self._emit("notice", "error", str(exc))
            return
        except Exception as exc:
            logger.error("Falha na transcrição: %s", type(exc).__name__)
            self._drop_block(block)
            self._emit("notice", "error", "Não consegui transcrever o áudio. Tente de novo.")
            return
        finally:
            if epoch == self._epoch:
                self._recording_block = None

        if block is not None and block in self.draft:
            block.pending = None
            block.text = text.strip() or _NO_SPEECH
            self._emit("draft_changed", self.draft, None)

    async def _prepare_voice(self) -> None:
        # Vale para a entrada no módulo inteira (não muda com "Nova conversa");
        # stop() cancela esta task antes de soltar o listener.
        try:
            await self._get_asr()
        except SpeechUnavailable as exc:
            self._set_voice(VoiceStatus.UNAVAILABLE, str(exc))
            return
        self._set_voice(VoiceStatus.READY, "")

    # ------------------------------------------------------------------ foto

    def take_photo(self) -> bool:
        if self._camera is None:
            self._emit("notice", "error", "Câmera desativada nas configurações.")
            return False
        if self.busy:
            return False
        self._stop_speaking()
        self._run_activity(self._capture(), Activity.CAPTURING)
        return True

    async def _capture(self) -> None:
        try:
            image = await self._camera.capture()
        except CameraError as exc:
            self._emit("notice", "error", f"Não consegui tirar a foto: {exc}")
            return
        self._photo_count += 1
        block = DraftBlock(
            id=next(self._ids), kind="photo", image=image, label=f"foto {self._photo_count}"
        )
        self.draft.append(block)
        self._emit("draft_changed", self.draft, None)

    # ------------------------------------------------------------------ envio

    def send(self) -> bool:
        """Envia o rascunho inteiro como UMA mensagem. Retorna False se não havia o que enviar."""
        if self.busy:
            return False
        blocks = [b for b in self.draft if not b.is_empty]
        if not blocks:
            self._emit("notice", "info", "Fale, escreva ou tire uma foto antes de enviar.")
            return False
        self._stop_speaking()
        self.draft = []
        self._sending = blocks
        self._emit("draft_changed", self.draft, None)
        self._run_activity(self._send(blocks, self._epoch), Activity.THINKING)
        return True

    async def _send(self, blocks: list[DraftBlock], epoch: int) -> None:
        parts: list[Any] = [b.image if b.kind == "photo" else b.text.strip() for b in blocks]
        question = ChatMessage(id=next(self._ids), role="user", blocks=list(blocks))
        reply = ChatMessage(id=next(self._ids), role="ai", status="thinking")
        self.messages += [question, reply]
        self._emit("message_added", question)
        self._emit("message_added", reply)

        chunker = SentenceChunker()
        try:
            async for token in self._llm.send_parts_stream(parts):
                if reply.status == "thinking":
                    reply.status = "streaming"
                    self._set_activity(Activity.RESPONDING)
                reply.text += token
                self._emit("message_updated", reply)
                if self.voice_output:
                    for phrase in chunker.feed(token):
                        self._tts.speak(phrase)
        except asyncio.CancelledError:
            if epoch == self._epoch:  # cancelado pelo aluno, não por saída/conversa nova
                reply.status = "cancelled"
                self._emit("message_updated", reply)
                self._restore_draft(blocks)
            raise
        except Exception as exc:
            reply.status = "error"
            reply.error = describe_error(exc)
            if not isinstance(exc, LLMError):
                logger.error("Erro inesperado no envio: %s", type(exc).__name__)
            self._emit("message_updated", reply)
            self._restore_draft(blocks)
            self._emit("notice", "error", reply.error)
            return
        finally:
            self._sending = []

        if not reply.text.strip():
            reply.status = "error"
            reply.error = "A IA não respondeu nada. Tente de novo."
            self._emit("message_updated", reply)
            self._restore_draft(blocks)
            return

        rest = chunker.flush()
        if self.voice_output and rest:
            self._tts.speak(rest)
        reply.status = "done"
        self._emit("message_updated", reply)

        if self.voice_output and self._tts.is_busy():
            self._set_activity(Activity.SPEAKING)
            while self._tts.is_busy():
                await asyncio.sleep(_SPEAKING_POLL_S)

    # ------------------------------------------------------------------ cancelar / voz

    def cancel(self) -> None:
        """Interrompe a atividade em andamento (botão Parar)."""
        activity = self.activity
        if activity is Activity.RECORDING:
            self._run_activity(self._discard_recording())
            return
        if activity is Activity.SPEAKING:
            self._stop_speaking()
            return
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._llm.cancel_stream()
        self._tts.stop_speaking()
        if activity in (Activity.THINKING, Activity.RESPONDING):
            self._emit("notice", "info", "Resposta interrompida. Sua pergunta voltou para edição.")

    async def _discard_recording(self) -> None:
        await self._recorder.discard()
        self._drop_block(self._recording_block)
        self._recording_block = None
        self._emit("notice", "info", "Gravação descartada.")

    def set_voice_output(self, enabled: bool) -> None:
        self.voice_output = enabled
        if not enabled:
            self._stop_speaking()

    # ------------------------------------------------------------------ interno

    def _run_activity(self, coro: Coroutine, activity: Activity | None = None) -> None:
        if activity is not None:
            self._set_activity(activity)
        task = asyncio.create_task(coro, name="chat-activity")
        self._task = task
        task.add_done_callback(self._activity_done)

    def _activity_done(self, task: asyncio.Task) -> None:
        if task is not self._task:
            return
        self._task = None
        if not task.cancelled() and task.exception() is not None:
            logger.error("Atividade do chat falhou: %s", type(task.exception()).__name__)
            self._emit("notice", "error", "Algo deu errado. Tente de novo.")
        self._set_activity(Activity.IDLE)

    def _spawn_background(self, coro: Coroutine) -> None:
        task = asyncio.create_task(coro, name="chat-background")
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _abort_everything(self) -> None:
        """Avança a época e encerra atividade, stream e fala em andamento."""
        self._epoch += 1
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._recorder is not None and self._recorder.recording:
            await self._recorder.discard()
        self._llm.cancel_stream()
        self._tts.stop_speaking()
        self._recording_block = None
        self._sending = []

    def _wipe(self) -> None:
        self.draft = []
        self.messages = []
        self._photo_count = 0

    def _restore_draft(self, blocks: list[DraftBlock]) -> None:
        self.draft = list(blocks) + self.draft
        self._emit("draft_changed", self.draft, None)

    def _drop_block(self, block: DraftBlock | None) -> None:
        if block is not None and block in self.draft:
            self.draft.remove(block)
            self._emit("draft_changed", self.draft, None)

    def _set_pending(self, block: DraftBlock | None, pending: str) -> None:
        if block is not None and block in self.draft:
            block.pending = pending
            self._emit("draft_changed", self.draft, None)

    def _find(self, block_id: int) -> DraftBlock | None:
        return next((b for b in self.draft if b.id == block_id), None)

    def _stop_speaking(self) -> None:
        """Cala o TTS. Se a resposta anterior ainda estava falando, encerra aquela
        tarefa aqui — senão o fim dela sobrescreveria a atividade nova."""
        if self.activity is Activity.SPEAKING:
            task, self._task = self._task, None
            if task is not None and not task.done():
                task.cancel()
            self._set_activity(Activity.IDLE)
        if self._tts.is_busy():
            self._tts.stop_speaking()

    def _set_activity(self, activity: Activity) -> None:
        if activity is not self.activity:
            self.activity = activity
            self._emit("activity_changed", activity)

    def _set_voice(self, status: VoiceStatus, reason: str) -> None:
        self.voice_status = status
        self.voice_reason = reason or ""
        self._emit("voice_status_changed", status, self.voice_reason)

    def _emit(self, event: str, *args: Any) -> None:
        listener = self.listener
        if listener is None:
            return
        try:
            getattr(listener, event)(*args)
        except Exception:
            logger.exception("Erro ao atualizar a tela do chat (%s).", event)
