"""Tela do chat (modules/chat/Page.qml) com Qt Quick de verdade (offscreen):
o que o aluno toca e vê. A lógica do controller tem os testes em
test_chat_controller.py; o teclado da tela, em test_keyboard.py."""

import asyncio

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QTextCursor
from qthelpers import click, find, find_all, key, label, pump, until

from modules.chat import ChatModule
from modules.chat.session import Activity


async def open_chat(make_app, **kwargs):
    app = make_app(modules=lambda s: [ChatModule(s)], **kwargs)
    await app.enter_module(app.modules[0])
    await pump(0.4)
    return app, app.window, app.page


def write(controller, text):
    cursor = QTextCursor(controller.editor.document)
    cursor.setPosition(controller.editor.length)
    cursor.insertText(text)


async def appears(window, name):
    """Espera o item aparecer e o popup terminar de se posicionar (abrir anima)."""
    await until(lambda: find(window, name) is not None)
    await pump(0.25)


async def idle(app):
    session = app.modules[0].session
    await until(lambda: session.activity is Activity.IDLE and session._task is None)
    await pump(0.1)


async def test_layout_cabe_em_1024x600_com_alvos_de_48px(make_app):
    app, window, _c = await open_chat(make_app)
    for name in ("backButton", "moreButton", "micButton", "photoButton", "sendButton"):
        button = find(window, name)
        assert button is not None, name
        assert button.width() >= 48 and button.height() >= 48, name
        bottom = button.mapToScene(button.boundingRect().bottomRight())
        assert bottom.y() <= window.height() and bottom.x() <= window.width(), name
    assert find(window, "history").height() >= 160


async def test_enviar_so_com_conteudo_e_vira_parar_sem_envio_duplicado(make_app):
    app, window, controller = await open_chat(make_app)
    app.services.llm.gate = asyncio.Event()
    send = find(window, "sendButton")
    assert send.property("enabled") is False

    write(controller, "quanto é 2+2?")
    await pump()
    assert send.property("enabled") is True
    click(window, send)
    await pump(0.1)
    assert label(send) == "■ Parar resposta"
    click(window, send)  # o mesmo lugar agora para
    await idle(app)
    assert len(app.services.llm.sent) == 1
    assert label(send) == "Enviar ➤"
    assert controller.editor.items() == ["quanto é 2+2?"]  # a pergunta voltou


async def test_resposta_em_markdown_no_balao(make_app):
    app, window, controller = await open_chat(make_app)
    app.services.llm.tokens = ["**Quatro**", ", com certeza."]
    write(controller, "quanto é 2+2?")
    click(window, find(window, "sendButton"))
    await idle(app)
    texts = [label(i) for i in find_all(window, "replyText")]
    assert texts[-1] == "**Quatro**, com certeza."  # Text.MarkdownText desenha o negrito


async def test_ctrl_enter_envia_e_esc_cancela(make_app):
    app, window, controller = await open_chat(make_app)
    app.services.llm.gate = asyncio.Event()
    click(window, find(window, "editor"))
    write(controller, "pergunta")
    await pump()
    key(window, Qt.Key.Key_Return)  # Enter quebra a linha
    await pump()
    assert app.services.llm.sent == []
    key(window, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    await pump(0.1)
    assert len(app.services.llm.sent) == 1
    key(window, Qt.Key.Key_Escape)
    await idle(app)
    assert app.modules[0].session.messages[-1].status == "cancelled"


async def test_previa_da_foto_usar_tirar_outra_e_cancelar(make_app):
    app, window, controller = await open_chat(make_app)
    click(window, find(window, "photoButton"))
    await appears(window, "previewUse")
    click(window, find(window, "previewRetake"))
    await until(lambda: app.services.camera.count == 2 and find(window, "previewUse") is not None)
    click(window, find(window, "previewUse"))
    await pump(0.3)
    assert find(window, "previewUse") is None
    photos = [x for x in controller.editor.items() if isinstance(x, int)]
    assert len(photos) == 1

    click(window, find(window, "photoButton"))
    await appears(window, "previewCancel")
    click(window, find(window, "previewCancel"))
    await pump(0.3)
    assert [x for x in controller.editor.items() if isinstance(x, int)] == photos


async def test_tocar_na_foto_do_editor_abre_remover(make_app):
    app, window, controller = await open_chat(make_app)
    controller.takePhoto(0)
    await appears(window, "previewUse")
    click(window, find(window, "previewUse"))
    await pump(0.3)
    editor = find(window, "editor")
    # A foto é o primeiro caractere: miniatura de 72 px de altura logo depois
    # do padding (12 px) do editor.
    point = editor.mapToScene(QPointF(12 + 20, 12 + 36)).toPoint()
    click(window, editor, point)
    await appears(window, "previewRemove")
    click(window, find(window, "previewRemove"))
    await pump(0.3)
    assert controller.editor.items() == []

    # Tocar no texto não abre nada.
    write(controller, "texto")
    await pump()
    click(window, editor, editor.mapToScene(QPointF(30, 24)).toPoint())
    await pump(0.3)
    assert find(window, "previewRemove") is None


async def test_erro_da_camera_tentar_de_novo_no_aviso(make_app):
    app, window, _c = await open_chat(make_app)
    app.services.camera.fail = True
    click(window, find(window, "photoButton"))
    await appears(window, "toastAction")
    assert "câmera não respondeu" in label(find(window, "toastText"))
    app.services.camera.fail = False
    click(window, find(window, "toastAction"))
    await appears(window, "previewUse")
    assert find(window, "toast") is None  # o aviso saiu


async def test_sair_com_pergunta_pede_confirmacao(make_app):
    app, window, controller = await open_chat(make_app)
    write(controller, "pela metade")
    await pump()
    click(window, find(window, "backButton"))
    await appears(window, "dialogConfirm")
    click(window, find(window, "dialogCancel"))  # "Continuar aqui"
    await pump(0.3)
    assert app.active is not None

    click(window, find(window, "backButton"))
    await appears(window, "dialogConfirm")
    click(window, find(window, "dialogConfirm"))
    await until(lambda: app.active is None)


async def test_menu_mais_nova_conversa_pede_confirmacao(make_app):
    app, window, controller = await open_chat(make_app)
    write(controller, "pergunta")
    click(window, find(window, "sendButton"))
    await idle(app)
    click(window, find(window, "moreButton"))
    await appears(window, "newItem")
    assert "✓" in label(find(window, "voiceItem"))  # ler respostas: ligado
    click(window, find(window, "newItem"))
    await appears(window, "dialogConfirm")
    click(window, find(window, "dialogConfirm"))
    await until(lambda: len(controller.messages.rows) == 1)
    assert controller.property("toastText") == "Conversa apagada."


async def test_ler_respostas_some_do_menu_sem_voz(make_app):
    app, window, _c = await open_chat(make_app, voice_output=False)
    click(window, find(window, "moreButton"))
    await appears(window, "newItem")
    assert find(window, "voiceItem") is None


async def test_nova_resposta_avisa_quando_o_historico_esta_rolado(make_app):
    app, window, controller = await open_chat(make_app)
    app.services.llm.tokens = ["linha\n\n" * 30]
    for n in range(2):
        write(controller, f"pergunta {n}")
        controller.send()
        await idle(app)
    history = find(window, "history")
    assert history.property("atYEnd") is True  # segue o fim enquanto ninguém rola

    # Enquanto a próxima resposta chega, o aluno rola para o começo.
    app.services.llm.gate = asyncio.Event()
    app.services.llm.tokens = ["primeiro trecho ", "linha\n\n" * 30]
    write(controller, "mais uma")
    controller.send()  # enviar volta a seguir o fim
    await pump(0.2)
    history.setProperty("contentY", 0)
    history.setProperty("follow", False)
    app.services.llm.gate.set()
    await idle(app)
    jump = find(window, "jumpButton")
    assert jump is not None
    assert history.property("contentY") == 0  # não puxou a tela de quem está lendo
    click(window, jump)
    await pump(0.2)
    assert history.property("atYEnd") is True
    assert find(window, "jumpButton") is None


async def test_sem_camera_o_botao_foto_nao_aparece(make_app):
    app, window, _c = await open_chat(make_app, camera=False)
    assert find(window, "photoButton") is None
