"""ChatController (modules/chat/controller.py): o estado que a tela do chat
desenha e as ações dela, sem QML. O editor é um QTextDocument comum."""

import pytest
from fakes import FakeASR, FakeCamera, FakeLLM, FakeRecorder, FakeTTS
from PySide6.QtGui import QTextCursor, QTextDocument
from qthelpers import pump, until

from api.llm_client import LLMError
from modules.chat.controller import ChatController
from modules.chat.session import Activity, ChatSession
from ui import images


@pytest.fixture
async def chat(qapp):
    llm, tts, recorder, asr, camera = FakeLLM(), FakeTTS(), FakeRecorder(), FakeASR(), FakeCamera()

    async def get_asr():
        return asr

    session = ChatSession(llm, tts, camera=camera, recorder=recorder, get_asr=get_asr)
    backs = []
    tasks = []

    def spawn(coro):
        import asyncio

        tasks.append(asyncio.get_running_loop().create_task(coro))

    controller = ChatController(
        session, lambda: backs.append(1), voice_output_available=True, spawn=spawn
    )
    session.listener = controller
    document = QTextDocument()
    controller.attach_document(document)
    await session.start()
    await pump(0.05)

    class Parts:
        pass

    parts = Parts()
    parts.c, parts.session, parts.llm, parts.tts = controller, session, llm, tts
    parts.recorder, parts.asr, parts.camera, parts.doc = recorder, asr, camera, document
    parts.backs = backs
    yield parts
    await session.stop()
    controller.close()


def write(parts, text, position=None):
    cursor = QTextCursor(parts.doc)
    cursor.setPosition(parts.c.editor.length if position is None else position)
    cursor.insertText(text)
    parts.c.editorChanged()  # o TextArea avisa a cada edição


def p(controller, name):
    return controller.property(name)


async def idle(parts):
    await until(lambda: parts.session.activity is Activity.IDLE and parts.session._task is None)
    await pump(0.08)


# ---------- estado inicial e rascunho ----------


async def test_boas_vindas_e_enviar_desativado_sem_conteudo(chat):
    rows = chat.c.messages.rows
    assert [(r["role"], r["text"]) for r in rows] == [
        ("ai", "Oi! Sobre o que você quer aprender hoje?")
    ]
    assert p(chat.c, "sendLabel") == "Enviar ➤" and p(chat.c, "sendEnabled") is False
    assert p(chat.c, "micLabel") == "● Falar" and p(chat.c, "micEnabled") is True
    assert p(chat.c, "historyLabel") == "▴ Ver conversa"

    write(chat, "quanto é 2+2?")
    assert [b.text for b in chat.session.draft] == ["quanto é 2+2?"]
    assert p(chat.c, "sendEnabled") is True


async def test_resumo_conta_fotos_e_palavras_e_atalhos_do_teclado_fisico(chat):
    write(chat, "olha isto aqui")
    assert p(chat.c, "summary") == ""  # só texto: nada a resumir
    chat.c.takePhoto(4)
    await idle(chat)
    assert p(chat.c, "summary") == "1 foto · 3 palavras"
    chat.c.physicalKey()
    assert p(chat.c, "summary").endswith("Ctrl+Enter envia · Esc cancela")


# ---------- fotos ----------


async def test_foto_entra_no_cursor_com_previa_e_a_ordem_enviada_e_a_visual(chat):
    previews = []
    chat.c.photoPreview.connect(lambda *args: previews.append(args))
    focus = []
    chat.c.focusEditor.connect(focus.append)
    write(chat, "antes depois")

    chat.c.takePhoto(6)  # cursor entre "antes " e "depois"
    assert p(chat.c, "photoLabel") == "Tirando foto…" and p(chat.c, "photoEnabled") is False
    await idle(chat)
    photo_id = next(b.id for b in chat.session.draft if b.kind == "photo")
    assert chat.c.editor.items() == ["antes ", photo_id, "depois"]
    assert focus[-1] == 7  # cursor logo depois da foto
    ((block_id, is_new, url, label),) = previews
    assert (block_id, is_new, label) == (photo_id, True, "Foto 1")
    assert url.startswith("image://hai/photo/")
    assert chat.c.photoAt(6) == photo_id and chat.c.photoAt(0) == -1

    chat.c.send()
    await idle(chat)
    assert chat.llm.sent[-1][0] == "antes"
    assert [type(x).__name__ for x in chat.llm.sent[-1]] == ["str", "CapturedImage", "str"]
    user = chat.c.messages.rows[1]
    assert [part["kind"] for part in user["parts"]] == ["text", "photo", "text"]


async def test_tirar_outra_troca_no_mesmo_lugar_e_remover_tira_do_envio(chat):
    write(chat, "a b")
    chat.c.takePhoto(2)
    await idle(chat)
    first = next(b.id for b in chat.session.draft if b.kind == "photo")

    chat.c.retakePhoto(first)
    await idle(chat)
    items = chat.c.editor.items()
    (second,) = [x for x in items if isinstance(x, int)]
    assert second != first and items == ["a ", second, "b"]
    assert chat.camera.count == 2

    chat.c.removePhoto(second)
    await pump()
    assert chat.c.editor.items() == ["a b"]
    assert not any(b.kind == "photo" for b in chat.session.draft)


async def test_apagar_a_foto_no_editor_tira_ela_do_envio(chat):
    chat.c.takePhoto(0)
    await idle(chat)
    write(chat, "texto")
    cursor = QTextCursor(chat.doc)
    cursor.setPosition(1)
    cursor.deletePreviousChar()  # ⌫ logo depois da foto
    chat.c.editorChanged()
    assert [b.kind for b in chat.session.draft] == ["text"]


async def test_erro_da_camera_oferece_tentar_de_novo(chat):
    chat.camera.fail = True
    chat.c.takePhoto(0)
    await idle(chat)
    assert p(chat.c, "toastKind") == "error"
    assert "câmera não respondeu" in p(chat.c, "toastText")
    assert p(chat.c, "toastAction") == "Tentar de novo"
    assert chat.c.editor.items() == []  # o espaço reservado saiu

    chat.camera.fail = False
    chat.c.noticeAction(0)
    await idle(chat)
    assert p(chat.c, "toastText") == ""  # o erro sai do caminho
    assert any(b.kind == "photo" and b.image is not None for b in chat.session.draft)


# ---------- voz ----------


async def test_falar_por_toque_insere_no_cursor(chat):
    write(chat, "começo  fim")
    chat.c.micPressed(7)
    chat.c.micReleased()  # toque curto: continua gravando
    await pump()
    assert chat.session.activity is Activity.RECORDING
    assert p(chat.c, "recording") is True and p(chat.c, "micLabel") == "■ Parar gravação"
    assert p(chat.c, "micKind") == "danger"
    pending = next(b.id for b in chat.session.draft if b.pending)
    assert chat.c.editor.items() == ["começo ", pending, " fim"]

    chat.c.micPressed(0)  # segundo toque termina
    chat.c.micReleased()
    await idle(chat)
    assert chat.c.editor.items() == ["começo quanto é dois mais dois fim"]


async def test_segurar_e_soltar_tambem_grava(chat):
    chat.c.micPressed(0)
    chat.c._mic_pressed_at -= 1.0  # segurou 1 s (o limite é 0,4 s)
    chat.c.micReleased()
    await idle(chat)
    assert chat.c.editor.items() == ["quanto é dois mais dois"]


async def test_microfone_mudo_avisa_e_nao_escreve_no_editor(chat):
    chat.recorder.audio = b"\x00\x00" * 8000
    write(chat, "minha pergunta")
    chat.c.micPressed(14)
    chat.c.micPressed(14)
    await idle(chat)
    assert chat.c.editor.items() == ["minha pergunta"]
    assert p(chat.c, "toastKind") == "error"
    assert "microfone não captou som" in p(chat.c, "toastText")
    assert chat.asr.calls == 0


async def test_gravacao_tem_limite_de_tempo(chat, monkeypatch):
    chat.c._recording_timer.setInterval(30)  # 60 s na aplicação
    chat.c.micPressed(0)
    chat.c.micReleased()
    await until(lambda: chat.session.activity is not Activity.RECORDING)
    await idle(chat)
    assert chat.c.editor.items() == ["quanto é dois mais dois"]


# ---------- envio e resposta ----------


async def test_enviar_vira_parar_durante_a_resposta_sem_envio_duplicado(chat):
    chat.llm.gate = __import__("asyncio").Event()
    sent = []
    chat.c.sent.connect(lambda: sent.append(1))
    write(chat, "pergunta")
    chat.c.sendOrStop()
    await pump()
    assert sent == [1]  # a tela fecha o teclado
    assert p(chat.c, "sendLabel") == "■ Parar resposta" and p(chat.c, "sendKind") == "danger"
    assert chat.c.editor.items() == []
    chat.c.send()  # toque repetido não envia de novo
    assert len(chat.llm.sent) == 1

    chat.c.sendOrStop()  # agora é Parar
    await idle(chat)
    assert chat.c.messages.rows[-1]["status"] == "cancelled"
    assert chat.c.editor.items() == ["pergunta"]  # a pergunta voltou ao editor
    assert "Resposta interrompida" in p(chat.c, "toastText")


async def test_streaming_agrupa_as_atualizacoes_do_balao(chat):
    chat.llm.tokens = [f"t{i} " for i in range(150)]
    changes = []
    chat.c.messages.dataChanged.connect(lambda *_a: changes.append(1))
    write(chat, "conte até 150")
    chat.c.send()
    await idle(chat)
    reply = chat.c.messages.rows[-1]
    assert reply["status"] == "done"
    assert reply["text"] == "".join(chat.llm.tokens)
    assert len(changes) < 20  # 150 trechos, poucas atualizações do balão


async def test_pensando_e_depois_a_resposta(chat):
    chat.llm.gate = __import__("asyncio").Event()
    chat.llm.tokens = ["Ol", "á"]
    write(chat, "oi")
    chat.c.send()
    await pump()
    assert chat.c.messages.rows[-1]["status"] in ("thinking", "streaming")
    assert chat.c.messages.rows[-1]["startedAt"] > 0
    chat.llm.gate.set()
    await idle(chat)
    assert chat.c.messages.rows[-1]["text"] == "Olá"
    assert p(chat.c, "historyLabel") == "▴ Ver conversa (2 mensagens)"


async def test_erro_persiste_e_tentar_de_novo_so_no_ultimo(chat):
    chat.llm.error = LLMError("A IA demorou demais para responder.")
    write(chat, "primeira")
    chat.c.send()
    await idle(chat)
    first = chat.c.messages.rows[-1]
    assert first["status"] == "error" and first["retry"] is True
    assert p(chat.c, "toastKind") == "error"
    assert chat.c.editor.items() == ["primeira"]
    await pump(0.1)
    assert p(chat.c, "toastText") != ""  # erro não some sozinho

    chat.c.send()  # "↻ Tentar de novo"
    await idle(chat)
    rows = chat.c.messages.rows
    assert [r["retry"] for r in rows if r["status"] == "error"] == [False, True]


async def test_aviso_informativo_some_sozinho(chat):
    chat.c._toast_timer.setInterval(30)  # 5 s na aplicação
    chat.c.notice("info", "Conversa apagada.")
    assert p(chat.c, "toastKind") == "info"
    await until(lambda: p(chat.c, "toastText") == "")


async def test_escrever_interrompe_a_leitura(chat):
    write(chat, "oi")
    chat.c.send()  # enviar cala a fala anterior; a desta resposta começa agora
    chat.tts.busy = True
    await until(lambda: chat.session.activity is Activity.SPEAKING)
    assert p(chat.c, "sendLabel") == "■ Parar leitura"
    write(chat, "outra")
    await pump()
    assert chat.session.activity is Activity.IDLE
    assert chat.tts.stops >= 1


# ---------- sair e nova conversa ----------


async def test_sair_sem_pergunta_sai_direto_e_com_pergunta_pede_confirmacao(chat):
    asks = []
    chat.c.confirmRequested.connect(asks.append)
    chat.c.requestBack()
    assert chat.backs == [1] and asks == []

    write(chat, "pergunta pela metade")
    chat.c.requestBack()
    assert asks == ["back"] and chat.backs == [1]
    chat.c.back()  # confirmou
    assert chat.backs == [1, 1]


async def test_nova_conversa_apaga_tudo_e_as_fotos(chat):
    chat.c.takePhoto(0)
    await idle(chat)
    write(chat, "pergunta")
    chat.c.send()
    await idle(chat)
    assert images.stored() >= 1

    chat.c.newConversation()
    await until(lambda: len(chat.c.messages.rows) == 1)
    await pump()
    assert chat.c.messages.rows[0]["msgId"] == 0  # só as boas-vindas
    assert chat.c.editor.items() == []
    assert p(chat.c, "toastText") == "Conversa apagada."
    assert images.stored() == 0


async def test_voz_das_respostas_liga_e_desliga(chat):
    assert p(chat.c, "voiceOutput") is True
    chat.c.setVoiceOutput(False)
    assert p(chat.c, "voiceOutput") is False and chat.session.voice_output is False


async def test_depois_de_fechar_nada_mais_chega(chat):
    chat.c.close()
    chat.c.notice("error", "tarde demais")
    chat.c.send()
    chat.c.takePhoto(0)
    assert p(chat.c, "toastText") == ""
    assert chat.llm.sent == [] and chat.camera.count == 0
