"""Aplicação gráfica com Tk de verdade: menu, navegação, ciclo de vida e layout.

Precisa de um servidor X ($DISPLAY). Sem ele (CI headless), os testes são pulados.
Os serviços são dublês (tests/fakes.py): nada de rede, microfone ou câmera.
"""

import asyncio
import tkinter as tk

import pytest
from fakes import FakeServices

from core.app import App
from modules import build_modules
from modules.chat import ChatModule
from modules.chat.session import Activity


@pytest.fixture(scope="module")
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"sem servidor X para o Tk: {exc}")
    window.geometry("1024x600+0+0")
    yield window
    window.destroy()


@pytest.fixture
def make_app(root):
    apps = []

    def factory(**kwargs):
        services = FakeServices(**kwargs)
        app = App(services, build_modules(services), root=root)
        app.build()
        apps.append(app)
        pump(root)
        return app

    yield factory
    for app in apps:
        if app._container is not None:
            app._container.destroy()
    pump(root)


def pump(root, n=3):
    for _ in range(n):
        root.update()


async def settle(root, seconds=0.05):
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while loop.time() < end:
        root.update()
        await asyncio.sleep(0.005)


async def until(root, predicate, timeout=2.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError("condição não atingida a tempo")
        root.update()
        await asyncio.sleep(0.005)


def descendants(widget):
    out = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(descendants(child))
    return out


async def type_text(view, root, text):
    """Toca em "Escrever" e digita no campo novo (o campo é a fonte da verdade)."""
    antes = set(view._draft_texts)
    view.write_button.invoke()
    await settle(root)
    (novo,) = set(view._draft_texts) - antes
    view._draft_texts[novo].insert("1.0", text)


def chat_of(app) -> ChatModule:
    return next(m for m in app.modules if isinstance(m, ChatModule))


# ---------- menu ----------


async def test_menu_aparece_com_apenas_o_modulo_de_conversa(make_app, root):
    app = make_app()
    assert app.menu.frame.winfo_ismapped()
    assert list(app.menu.cards) == ["chat"]
    labels = [
        w.cget("text") for w in descendants(app.menu.cards["chat"]) if isinstance(w, tk.Label)
    ]
    assert "Conversar com a IA" in labels
    assert app.menu.message == ""


async def test_problema_de_configuracao_aparece_no_menu(make_app, root):
    app = make_app(llm_problem="Chave da API não configurada.")
    assert "Chave da API" in app.menu.message
    assert await app.enter_module(chat_of(app)) is False  # não abre, explica
    assert app.active is None
    assert "Conversar com a IA" in app.menu.message


# ---------- navegação e recursos ----------


async def test_entrar_e_voltar_ao_menu(make_app, root):
    app = make_app()
    chat = chat_of(app)
    assert await app.enter_module(chat) is True
    await settle(root)
    assert app.active is chat
    assert not app.menu.frame.winfo_ismapped()
    recorder = app.services.recorders[-1]
    assert recorder.opened == 1  # microfone aberto (pausado) só dentro do módulo

    chat.view.back_button.invoke()  # botão "← Voltar" (toque)
    await until(root, lambda: app.active is None)
    await settle(root)
    assert app.menu.frame.winfo_ismapped()
    assert recorder.closed == 1
    assert chat.session is None and chat.view is None


async def test_navegacao_repetida_nao_acumula_recursos(make_app, root):
    app = make_app()
    chat = chat_of(app)
    tarefas_iniciais = len(asyncio.all_tasks())
    widgets_no_menu = len(descendants(root))
    timers_iniciais = len(root.tk.splitlist(root.tk.call("after", "info")))

    for _ in range(5):
        assert await app.enter_module(chat)
        await settle(root)
        chat.view.notice("info", "aviso com timer")  # cria um after()
        await app.leave_module()
        await settle(root)
        assert len(descendants(root)) == widgets_no_menu
        assert len(asyncio.all_tasks()) <= tarefas_iniciais

    assert len(root.tk.splitlist(root.tk.call("after", "info"))) <= timers_iniciais
    assert len(app.services.recorders) == 5
    assert all(r.opened == 1 and r.closed == 1 for r in app.services.recorders)
    assert app.services.llm.resets == 10  # entrada e saída: conversa nunca sobrevive


async def test_toque_duplo_no_cartao_abre_uma_vez(make_app, root):
    app = make_app()
    chat = chat_of(app)
    app.open_module(chat)
    app.open_module(chat)
    await until(root, lambda: app.active is chat)
    await settle(root)
    assert len(app.services.recorders) == 1
    await app.leave_module()


async def test_encerrar_o_app_libera_o_modulo_e_os_servicos(make_app, root):
    app = make_app()
    chat = chat_of(app)
    await app.enter_module(chat)
    await settle(root)
    recorder = app.services.recorders[-1]

    await app.shutdown()
    await app.shutdown()  # idempotente

    assert recorder.closed == 1
    assert app.services.closed == 1
    assert app.active is None
    assert root.winfo_exists()  # root dos testes não pertence ao app


async def test_falha_ao_abrir_o_modulo_volta_ao_menu_com_aviso(make_app, root, monkeypatch):
    app = make_app()
    chat = chat_of(app)

    async def quebra(*_a):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat, "enter", quebra)
    assert await app.enter_module(chat) is False
    pump(root)
    assert app.active is None
    assert app.menu.frame.winfo_ismapped()
    assert "Não foi possível abrir" in app.menu.message


# ---------- tela de conversa ----------


def _inside(widget, root):
    x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
    return (
        widget.winfo_ismapped()
        and x >= 0
        and y >= 0
        and x + widget.winfo_width() <= root.winfo_width()
        and y + widget.winfo_height() <= root.winfo_height()
    )


async def test_layout_cabe_em_1024x600(make_app, root):
    root.geometry("1024x600")
    app = make_app()
    await settle(root, 0.1)
    assert _inside(app.menu.cards["chat"], root)

    chat = chat_of(app)
    await app.enter_module(chat)
    await settle(root, 0.1)
    view = chat.view
    controles = [
        view.back_button,
        view.voice_button,
        view.new_button,
        view.mic_button,
        view.photo_button,
        view.write_button,
        view.send_button,
        view.conversation,
        view.prompt,
        view.status_label,
    ]
    for widget in controles:
        assert _inside(widget, root), widget
    # alvos de toque confortáveis, qualquer que seja a fonte instalada
    for widget in (
        view.back_button,
        view.new_button,
        view.mic_button,
        view.photo_button,
        view.write_button,
        view.send_button,
    ):
        assert widget.winfo_height() >= 44, widget
    assert view.conversation.winfo_height() >= 200
    await app.leave_module()


async def test_fluxo_completo_pela_tela_texto_foto_e_resposta(make_app, root):
    app = make_app()
    chat = chat_of(app)
    await app.enter_module(chat)
    await settle(root)
    view, session = chat.view, chat.session

    view.write_button.invoke()
    await settle(root)
    (campo,) = view._draft_texts.values()
    campo.insert("1.0", "que objeto é este?")  # sem evento de tecla (ex.: colar)
    view.photo_button.invoke()
    await until(root, lambda: session.activity is Activity.IDLE and len(session.draft) == 2)
    await settle(root)

    view.send_button.invoke()
    await until(root, lambda: session.activity is Activity.IDLE and session.messages)
    await settle(root)

    (enviado,) = app.services.llm.sent
    assert enviado[0] == "que objeto é este?"
    assert enviado[1].mime_type == "image/jpeg"
    _bubble, texto = view._message_widgets[session.messages[-1].id]
    assert "Olá!" in texto.get("1.0", "end")
    assert app.services.tts.spoken  # resposta falada
    await app.leave_module()


async def test_segurar_para_falar_pela_tela(make_app, root):
    app = make_app()
    chat = chat_of(app)
    await app.enter_module(chat)
    await settle(root)
    view, session = chat.view, chat.session
    assert view.mic_button.cget("state") == "normal"

    view.mic_button.event_generate("<ButtonPress-1>")
    await settle(root)
    assert session.activity is Activity.RECORDING
    assert "Gravando" in view.status_label.cget("text")
    view.mic_button.event_generate("<ButtonRelease-1>")
    await until(root, lambda: session.activity is Activity.IDLE and session.draft)
    await settle(root)

    assert session.draft[0].text == "quanto é dois mais dois"
    assert list(view._draft_texts.values())[0].get("1.0", "end-1c") == "quanto é dois mais dois"
    await app.leave_module()


async def test_erro_do_servico_aparece_e_a_tela_continua_usavel(make_app, root):
    from api.llm_client import LLMError

    app = make_app()
    chat = chat_of(app)
    await app.enter_module(chat)
    await settle(root)
    app.services.llm.tokens = []
    app.services.llm.error = LLMError("Sem conexão com o serviço de IA.")
    view, session = chat.view, chat.session

    await type_text(view, root, "oi")
    view.send_button.invoke()
    await until(root, lambda: session.activity is Activity.IDLE and session.messages)
    await settle(root)

    assert "Sem conexão" in view.status_label.cget("text")
    _bubble, texto = view._message_widgets[session.messages[-1].id]
    assert "Sem conexão" in texto.get("1.0", "end")
    assert view.send_button.cget("state") == "normal"
    assert session.draft  # rascunho de volta para tentar de novo
    await app.leave_module()


async def test_nova_conversa_pela_tela_limpa_tudo(make_app, root):
    app = make_app()
    chat = chat_of(app)
    await app.enter_module(chat)
    await settle(root)
    view, session = chat.view, chat.session
    await type_text(view, root, "oi")
    view.send_button.invoke()
    await until(root, lambda: session.activity is Activity.IDLE and session.messages)

    view.new_button.invoke()
    await until(root, lambda: not session.messages)
    await settle(root)
    assert list(view._message_widgets) == [0]  # só a mensagem de boas-vindas
    assert "Conversa nova" in view.status_label.cget("text")
    await app.leave_module()
