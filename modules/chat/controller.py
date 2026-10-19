"""
Ponte entre a ChatSession e a tela (Page.qml): implementa ChatListener e
expõe à QML o estado já pronto para desenhar (rótulos, cores, habilitado) e os
slots das ações. A página não decide nada; os testes exercitam este objeto
sem QML.

Estados: não há linha de status. Cada estado aparece onde o aluno está
olhando: "Pensando… 0:12" no balão da IA, "gravando…" e "transcrevendo…" no
ponto do editor onde o texto vai entrar, o rótulo dos botões e o aviso (os
erros ficam até serem dispensados).

O editor (modules/chat/editor.py) é ligado em attachEditor(): o documento do
TextArea vira a fonte de cada replace_draft(), e draft_changed() o redesenha.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable, Coroutine

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from modules.chat.editor import Item, RichEditor
from modules.chat.session import Activity, ChatMessage, ChatSession, DraftBlock, VoiceStatus
from ui import images
from ui.models import ListModel

_HOLD_S = 0.4  # pressão maior que isso + soltar = "segurar para falar"
_MAX_RECORDING_S = 60
_INFO_MS = 5000  # avisos informativos somem sozinhos; erros, não
# Trechos do LLM chegam a dezenas por segundo; durante o streaming o balão é
# atualizado no máximo a cada _STREAM_PAINT_MS. O estado final vai na hora.
_STREAM_PAINT_MS = 50

_WELCOME = "Oi! Sobre o que você quer aprender hoje?"
_STOP_LABELS = {
    Activity.TRANSCRIBING: "■ Parar",
    Activity.CAPTURING: "■ Parar",
    Activity.THINKING: "■ Parar resposta",
    Activity.RESPONDING: "■ Parar resposta",
    Activity.SPEAKING: "■ Parar leitura",
}
_ROLES = ["msgId", "role", "text", "status", "error", "parts", "startedAt", "retry"]
_entries = itertools.count(1)


def _blocks_for(items: list[Item]) -> list[Item]:
    """Itens que replace_draft transforma em blocos (strings vazias somem)."""
    return [item for item in items if not (isinstance(item, str) and not item)]


class ChatController(QObject):
    stateChanged = Signal()
    toastChanged = Signal()
    # Pedidos à página (ela é quem mexe no foco, no teclado e nos diálogos).
    photoPreview = Signal(int, bool, str, str)  # id do bloco, foto nova?, endereço, rótulo
    confirmRequested = Signal(str)  # "back"
    focusEditor = Signal(int)  # posição do cursor
    sent = Signal()

    def __init__(
        self,
        session: ChatSession,
        go_back: Callable[[], None],
        *,
        voice_output_available: bool,
        spawn: Callable[[Coroutine], None],
    ):
        super().__init__()
        self._session = session
        self._go_back = go_back
        self._spawn = spawn
        self._voice_output_available = voice_output_available
        self._prefix = f"chat{next(_entries)}-"
        self._closed = False
        self._editor: RichEditor | None = None
        self._document_ref: QObject | None = None  # sem referência, o PySide solta o C++
        self._physical_keyboard = False
        self._recording_since: float | None = None
        self._mic_pressed_at = 0.0
        self._ignore_release = False
        self._toast = ("", "", "")  # (tipo, texto, rótulo da ação)
        self._toast_action_id: str | None = None
        self._pending_paint: dict[int, ChatMessage] = {}

        self.messages = ListModel(_ROLES, self)
        self._toast_timer = _single_shot(self, _INFO_MS, self.dismissNotice)
        self._paint_timer = _single_shot(self, _STREAM_PAINT_MS, self._flush_paints)
        self._recording_timer = _single_shot(
            self, _MAX_RECORDING_S * 1000, self._session.finish_recording
        )
        self.conversation_cleared()

    # ------------------------------------------------------------------ propriedades

    def _mic(self) -> tuple[str, str, bool]:
        status, activity = self._session.voice_status, self._session.activity
        if activity is Activity.RECORDING:
            return "■ Parar gravação", "danger", True
        if status is VoiceStatus.LOADING:
            return "Preparando microfone…", "success", False
        if status is VoiceStatus.UNAVAILABLE:
            return "Voz indisponível", "success", False
        return "● Falar", "success", not self._session.busy

    def _send(self) -> tuple[str, str, bool]:
        activity = self._session.activity
        if activity in _STOP_LABELS:
            return _STOP_LABELS[activity], "danger", True
        has_content = any(not b.is_empty for b in self._session.draft)
        return "Enviar ➤", "primary", activity is Activity.IDLE and has_content

    def _get_mic_label(self) -> str:
        return self._mic()[0]

    def _get_mic_kind(self) -> str:
        return self._mic()[1]

    def _get_mic_enabled(self) -> bool:
        return self._mic()[2]

    def _get_recording(self) -> bool:
        return self._session.activity is Activity.RECORDING

    def _get_recording_started(self) -> float:
        since = self._recording_since or time.monotonic()
        return (time.time() - (time.monotonic() - since)) * 1000  # ms, como Date.now()

    def _get_photo_visible(self) -> bool:
        return self._session.camera_available

    def _get_photo_label(self) -> str:
        return "Tirando foto…" if self._session.activity is Activity.CAPTURING else "Foto"

    def _get_photo_enabled(self) -> bool:
        return not self._session.busy

    def _get_send_label(self) -> str:
        return self._send()[0]

    def _get_send_kind(self) -> str:
        return self._send()[1]

    def _get_send_enabled(self) -> bool:
        return self._send()[2]

    def _get_summary(self) -> str:
        draft = self._session.draft
        photos = sum(1 for b in draft if b.kind == "photo" and b.image is not None)
        words = sum(len(b.text.split()) for b in draft if b.kind == "text")
        parts = []
        if photos:
            parts.append("1 foto" if photos == 1 else f"{photos} fotos")
            parts.append("1 palavra" if words == 1 else f"{words} palavras")
        if self._physical_keyboard:
            parts.append("Ctrl+Enter envia · Esc cancela")
        return " · ".join(parts)

    def _get_history_label(self) -> str:
        count = len(self._session.messages)
        return "▴ Ver conversa" if count == 0 else f"▴ Ver conversa ({count} mensagens)"

    def _get_voice_output(self) -> bool:
        return self._session.voice_output

    def _get_voice_output_available(self) -> bool:
        return self._voice_output_available

    def _get_messages(self) -> QObject:
        return self.messages

    def _get_toast_kind(self) -> str:
        return self._toast[0]

    def _get_toast_text(self) -> str:
        return self._toast[1]

    def _get_toast_action(self) -> str:
        return self._toast[2]

    micLabel = Property(str, _get_mic_label, notify=stateChanged)
    micKind = Property(str, _get_mic_kind, notify=stateChanged)
    micEnabled = Property(bool, _get_mic_enabled, notify=stateChanged)
    recording = Property(bool, _get_recording, notify=stateChanged)
    recordingStartedAt = Property(float, _get_recording_started, notify=stateChanged)
    photoVisible = Property(bool, _get_photo_visible, constant=True)
    photoLabel = Property(str, _get_photo_label, notify=stateChanged)
    photoEnabled = Property(bool, _get_photo_enabled, notify=stateChanged)
    sendLabel = Property(str, _get_send_label, notify=stateChanged)
    sendKind = Property(str, _get_send_kind, notify=stateChanged)
    sendEnabled = Property(bool, _get_send_enabled, notify=stateChanged)
    summary = Property(str, _get_summary, notify=stateChanged)
    historyLabel = Property(str, _get_history_label, notify=stateChanged)
    voiceOutput = Property(bool, _get_voice_output, notify=stateChanged)
    voiceOutputAvailable = Property(bool, _get_voice_output_available, constant=True)
    messageModel = Property(QObject, _get_messages, constant=True)
    toastKind = Property(str, _get_toast_kind, notify=toastChanged)
    toastText = Property(str, _get_toast_text, notify=toastChanged)
    toastAction = Property(str, _get_toast_action, notify=toastChanged)

    # ------------------------------------------------------------------ editor

    @Slot(QObject)
    def attachEditor(self, text_document: QObject) -> None:  # noqa: N802
        """Liga o documento do TextArea (QQuickTextDocument) ao rascunho."""
        self._document_ref = text_document
        self.attach_document(text_document.textDocument())

    def attach_document(self, document) -> None:
        self._editor = RichEditor(document, self._prefix)
        self.draft_changed(self._session.draft, None)

    @property
    def editor(self) -> RichEditor | None:
        return self._editor

    @Slot()
    def editorChanged(self) -> None:  # noqa: N802
        if self._closed or self._editor is None or self._editor.rebuilding:
            return
        self._sync()
        if self._session.activity is Activity.SPEAKING:
            self._session.cancel()  # começar a escrever interrompe a leitura
        self.stateChanged.emit()

    @Slot(int, result=int)
    def photoAt(self, position: int) -> int:  # noqa: N802
        """Id da foto embutida na posição (o caractere logo depois dela), ou -1."""
        if self._editor is None:
            return -1
        block_id = self._editor.block_at(position)
        block = self._find(block_id) if block_id is not None else None
        return block.id if block is not None and block.image is not None else -1

    @Slot(int, result=int)
    def pastePlain(self, position: int) -> int:  # noqa: N802
        """Colar sem formatação (texto puro da área de transferência)."""
        text = QGuiApplication.clipboard().text() if QGuiApplication.instance() else ""
        if self._editor is None or not text:
            return position
        return self._editor.insert_plain(position, text)

    @Slot()
    def physicalKey(self) -> None:  # noqa: N802
        if not self._physical_keyboard:
            self._physical_keyboard = True
            self.stateChanged.emit()

    # ------------------------------------------------------------------ ações

    @Slot()
    def requestBack(self) -> None:  # noqa: N802
        """← Menu. Sair apaga a conversa (privacidade): com pergunta não enviada
        ou algo em andamento, a página pede confirmação antes."""
        if self._closed:
            return
        has_draft = any(not b.is_empty for b in self._session.draft) or not (
            self._editor is None or self._editor.is_empty
        )
        if has_draft or self._session.busy:
            self.confirmRequested.emit("back")
        else:
            self._go_back()

    @Slot()
    def back(self) -> None:
        if not self._closed:
            self._go_back()

    @Slot(int)
    def micPressed(self, cursor: int) -> None:  # noqa: N802
        if self._closed:
            return
        session = self._session
        if session.activity is Activity.RECORDING:
            self._ignore_release = True  # segundo toque: para aqui, não no soltar
            session.finish_recording()
            return
        if session.voice_status is not VoiceStatus.READY:
            self.notice("error", session.voice_reason or "Entrada por voz indisponível.")
            return
        if session.busy:
            return
        self._mic_pressed_at = time.monotonic()
        session.begin_recording(self._index_at(cursor))

    @Slot()
    def micReleased(self) -> None:  # noqa: N802
        if self._ignore_release:
            self._ignore_release = False
            return
        held = time.monotonic() - self._mic_pressed_at
        if self._session.activity is Activity.RECORDING and held >= _HOLD_S:
            self._session.finish_recording()  # modo "segurar e soltar"
        # toque curto: continua gravando até o próximo toque

    @Slot(int)
    def takePhoto(self, cursor: int) -> None:  # noqa: N802
        if not self._closed:
            self._session.take_photo(self._index_at(cursor))

    @Slot(int)
    def openPhoto(self, block_id: int) -> None:  # noqa: N802
        """Foto já no editor: a página mostra Fechar / Remover foto."""
        self._preview(block_id, new=False)

    @Slot(int)
    def removePhoto(self, block_id: int) -> None:  # noqa: N802
        if self._closed:
            return
        self._sync()
        self._session.remove_block(block_id)

    @Slot(int)
    def retakePhoto(self, block_id: int) -> None:  # noqa: N802
        """Tirar outra: a foto nova entra no mesmo lugar da descartada."""
        if self._closed:
            return
        self._sync()
        block = self._find(block_id)
        index = self._session.draft.index(block) if block is not None else None
        self._session.remove_block(block_id)
        self._session.take_photo(index)

    @Slot()
    def sendOrStop(self) -> None:  # noqa: N802
        if self._session.activity in _STOP_LABELS:
            self.cancel()
        else:
            self.send()

    @Slot()
    def send(self) -> None:
        if self._closed:
            return
        self._sync()
        if self._session.send():
            self.sent.emit()  # a página fecha o teclado: a resposta precisa do espaço

    @Slot()
    def cancel(self) -> None:
        if not self._closed and self._session.activity is not Activity.IDLE:
            self._session.cancel()

    @Slot()
    def newConversation(self) -> None:  # noqa: N802
        if not self._closed:
            self._spawn(self._session.new_conversation())

    @Slot(bool)
    def setVoiceOutput(self, enabled: bool) -> None:  # noqa: N802
        if not self._closed:
            self._session.set_voice_output(enabled)
            self.stateChanged.emit()

    @Slot()
    def dismissNotice(self) -> None:  # noqa: N802
        self._toast_timer.stop()
        if self._toast != ("", "", ""):
            self._toast = ("", "", "")
            self.toastChanged.emit()

    @Slot(int)
    def noticeAction(self, cursor: int) -> None:  # noqa: N802
        """Botão do aviso ("Tentar de novo" depois de falha da câmera)."""
        action = self._toast_action_id
        self.dismissNotice()
        if action == "retry_photo":
            self.takePhoto(cursor)

    # ------------------------------------------------------------------ ChatListener

    def activity_changed(self, activity: Activity) -> None:
        if self._closed:
            return
        if activity is not Activity.IDLE and self._toast[0] == "error":
            self.dismissNotice()  # nova tentativa: o erro anterior sai do caminho
        if activity is Activity.RECORDING:
            self._recording_since = time.monotonic()
            self._recording_timer.start()
        else:
            self._recording_since = None
            self._recording_timer.stop()
        self.stateChanged.emit()

    def voice_status_changed(self, status: VoiceStatus, reason: str) -> None:
        if not self._closed:
            self.stateChanged.emit()

    def draft_changed(self, blocks: list[DraftBlock], focus_id: int | None) -> None:
        if self._closed:
            return
        if self._editor is not None:
            position = self._editor.rebuild(blocks, focus_id)
            if position is not None:
                self.focusEditor.emit(position)
        self.stateChanged.emit()

    def photo_captured(self, block: DraftBlock) -> None:
        if not self._closed:
            self._preview(block.id, new=True)

    def message_added(self, message: ChatMessage) -> None:
        if self._closed:
            return
        for row, existing in enumerate(self.messages.rows):
            if existing["retry"]:
                self.messages.update(row, retry=False)  # pergunta nova: o erro já não é o último
        self.messages.append(self._row(message))
        self.stateChanged.emit()

    def message_updated(self, message: ChatMessage) -> None:
        if self._closed:
            return
        if message.status == "streaming":
            self._pending_paint[message.id] = message
            if not self._paint_timer.isActive():
                self._paint_timer.start()
            return
        self._pending_paint.pop(message.id, None)
        self._paint(message)

    def conversation_cleared(self) -> None:
        if self._closed:
            return
        self._pending_paint.clear()
        self.messages.clear()
        images.drop(self._prefix)
        self.messages.append(self._row(ChatMessage(id=0, role="ai", text=_WELCOME)))
        self.stateChanged.emit()

    def notice(self, kind: str, text: str, action: str | None = None) -> None:
        if self._closed or not text:
            return
        label = "Tentar de novo" if action == "retry_photo" else ""
        self._toast_action_id = action
        self._toast = (kind, text, label)
        self.toastChanged.emit()
        if kind == "error":
            self._toast_timer.stop()
        else:
            self._toast_timer.start()

    # ------------------------------------------------------------------ ciclo de vida

    def close(self) -> None:
        """Saída do módulo: nada mais chega à página (que pode estar animando a saída)."""
        self._closed = True
        for timer in (self._toast_timer, self._paint_timer, self._recording_timer):
            timer.stop()
        self._pending_paint.clear()
        images.drop(self._prefix)
        self._editor = None
        self._document_ref = None

    # ------------------------------------------------------------------ interno

    def _sync(self) -> None:
        """Editor → sessão (antes de enviar, gravar, fotografar ou remover)."""
        if self._editor is not None:
            self._session.replace_draft(self._editor.items())

    def _index_at(self, cursor: int) -> int | None:
        """Posição no rascunho onde entra o bloco novo: a do cursor no editor."""
        if self._editor is None:
            return None
        before, after = self._editor.split(max(0, min(cursor, self._editor.length)))
        self._session.replace_draft(before + after)
        return len(self._session.draft) - len(_blocks_for(after))

    def _find(self, block_id: int | None) -> DraftBlock | None:
        return next((b for b in self._session.draft if b.id == block_id), None)

    def _preview(self, block_id: int, *, new: bool) -> None:
        block = self._find(block_id)
        if self._closed or block is None or block.image is None:
            return
        url = images.put(f"{self._prefix}{block.id}", block.image.data)
        self.photoPreview.emit(block.id, new, url, block.label.capitalize())

    def _flush_paints(self) -> None:
        if self._closed:
            return
        pending, self._pending_paint = self._pending_paint, {}
        for message in pending.values():
            self._paint(message)

    def _paint(self, message: ChatMessage) -> None:
        row = self.messages.find("msgId", message.id)
        if row < 0:
            return
        latest = self._session.messages[-1] if self._session.messages else None
        self.messages.update(
            row,
            text=message.text,
            status=message.status,
            error=message.error,
            # "Tentar de novo" só no erro mais recente: a pergunta já voltou ao editor.
            retry=message.status == "error" and message is latest,
        )

    def _row(self, message: ChatMessage) -> dict:
        parts = []
        for block in message.blocks:
            if block.kind == "photo":
                url = (
                    images.put(f"{self._prefix}{block.id}", block.image.data)
                    if block.image is not None
                    else ""
                )
                parts.append({"kind": "photo", "url": url, "text": block.label})
            elif block.text.strip():
                parts.append({"kind": "text", "url": "", "text": block.text.strip()})
        return {
            "msgId": message.id,
            "role": message.role,
            "text": message.text,
            "status": message.status,
            "error": message.error,
            "parts": parts,
            "startedAt": time.time() * 1000,
            "retry": False,
        }


def _single_shot(parent: QObject, interval_ms: int, callback: Callable[[], None]) -> QTimer:
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(interval_ms)
    timer.timeout.connect(callback)
    return timer
