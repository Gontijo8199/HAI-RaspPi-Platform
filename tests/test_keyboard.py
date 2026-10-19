"""Teclado da tela (Qt Virtual Keyboard, ui/qml/Keyboard.qml e o estilo "hai")
integrado ao app: abre ao tocar no campo, ocupa espaço de verdade, digita e
fecha. Plataforma offscreen; a tela de toque real fica para o Pi."""

from PySide6.QtGui import QGuiApplication
from qthelpers import click, find, items, pump, until

from modules.chat import ChatModule
from modules.exemplo import ExampleModule


def keys(window, *labels):
    found = {}
    for item in items(window):
        text = item.property("text")
        if text in labels and "Key" in item.metaObject().className() and item.isVisible():
            found.setdefault(text, item)
    return found


async def open_chat(make_app, **kwargs):
    app = make_app(modules=lambda s: [ChatModule(s)], **kwargs)
    await app.enter_module(app.modules[0])
    await pump(0.4)
    return app


async def test_tocar_no_editor_abre_o_teclado_e_a_tela_encolhe(make_app):
    app = await open_chat(make_app)
    window = app.window
    stack = find(window, "stack")
    assert stack.height() == window.height()

    click(window, find(window, "editor"))
    await until(lambda: QGuiApplication.inputMethod().isVisible())
    await pump(0.3)
    panel = find(window, "inputPanel")
    assert panel.property("active") is True
    # O teclado tem altura de verdade (já houve um laço de layout que a zerava).
    assert 200 <= panel.height() <= window.height() * 0.5
    assert stack.height() == window.height() - panel.height()
    # O histórico vira uma prévia do fim da conversa, e o editor continua visível.
    assert find(window, "historyBar") is not None
    history = find(window, "history")
    assert history is not None and 30 <= history.height() <= 132
    composer = find(window, "composer")
    assert composer.mapToScene(composer.boundingRect().bottomLeft()).y() <= stack.height()


async def test_tecla_da_tela_escreve_no_editor_sem_virar_teclado_fisico(make_app):
    app = await open_chat(make_app)
    window = app.window
    click(window, find(window, "editor"))
    await until(lambda: QGuiApplication.inputMethod().isVisible())
    await pump(0.3)
    found = keys(window, "o", "i")
    for char in "oi":
        click(window, found[char])
        await pump(0.1)
    assert app.page.editor.items() == ["Oi"]  # maiúscula automática no começo
    assert app.page.property("sendEnabled") is True
    # As teclas da tela não contam como teclado físico (sem dica de atalhos).
    assert "Ctrl+Enter" not in app.page.property("summary")


async def test_ver_conversa_fecha_o_teclado_e_enviar_tambem(make_app):
    app = await open_chat(make_app)
    window = app.window
    click(window, find(window, "editor"))
    await until(lambda: QGuiApplication.inputMethod().isVisible())
    await pump(0.3)
    click(window, find(window, "historyBar"))
    await until(lambda: not QGuiApplication.inputMethod().isVisible())
    await pump(0.3)
    assert find(window, "history") is not None

    click(window, find(window, "editor"))
    await until(lambda: QGuiApplication.inputMethod().isVisible())
    found = keys(window, "a")
    click(window, found["a"])
    await pump(0.1)
    click(window, find(window, "sendButton"))
    await until(lambda: not QGuiApplication.inputMethod().isVisible())


async def test_estilo_claro_da_plataforma(make_app):
    app = await open_chat(make_app)
    window = app.window
    click(window, find(window, "editor"))
    await until(lambda: QGuiApplication.inputMethod().isVisible())
    await pump(0.3)
    image = window.grabWindow()
    panel = find(window, "inputPanel")
    corner = panel.mapToScene(panel.boundingRect().topLeft()).toPoint()
    background = image.pixelColor(corner.x() + 2, corner.y() + 2)
    assert background.lightness() > 200  # fundo claro, não o estilo escuro padrão


async def test_campo_numerico_abre_o_layout_de_numeros(make_app):
    app = make_app(modules=lambda s: [ExampleModule(s)])
    await app.enter_module(app.modules[0])
    await pump(0.4)
    window = app.window
    click(window, find(window, "numberField"))
    await until(lambda: QGuiApplication.inputMethod().isVisible())
    await pump(0.3)
    found = keys(window, "2", "8", "q")
    assert "2" in found and "8" in found and "q" not in found
    click(window, found["2"])
    click(window, found["8"])
    await pump(0.1)
    assert find(window, "numberField").property("text") == "28"


async def test_desligar_no_menu_mais_libera_a_tela_e_ligar_abre_o_teclado(make_app):
    app = await open_chat(make_app)
    window = app.window
    stack = find(window, "stack")
    click(window, find(window, "editor"))
    await until(lambda: QGuiApplication.inputMethod().isVisible())
    await pump(0.3)

    click(window, find(window, "moreButton"))
    await pump(0.3)
    click(window, find(window, "keyboardItem"))  # desliga
    await pump(0.4)
    assert app.controller.property("keyboardEnabled") is False
    assert stack.height() == window.height()  # teclado físico: a tela inteira
    assert find(window, "inputPanel") is None

    click(window, find(window, "moreButton"))
    await pump(0.3)
    assert "✓" not in find(window, "keyboardItem").property("text")
    click(window, find(window, "keyboardItem"))  # liga de novo: abre na hora
    await until(lambda: find(window, "inputPanel") is not None)
    await pump(0.3)
    assert find(window, "editor").hasActiveFocus()
    assert stack.height() < window.height()


async def test_sem_teclado_da_tela_o_painel_nem_carrega(make_app):
    app = await open_chat(make_app, keyboard=False)
    assert find(app.window, "inputPanel") is None
