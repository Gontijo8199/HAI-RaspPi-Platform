"""Aplicação gráfica com Qt Quick de verdade (offscreen): menu, navegação, ciclo
de vida e o módulo de exemplo. A tela do chat tem os testes em test_chat_page.py.
"""

import asyncio

from PySide6.QtCore import QObject, Qt
from qthelpers import (
    click,
    find,
    find_all,
    items,
    key,
    label,
    pump,
    screen_items,
    type_text,
    until,
)

from core.app import short_reason
from modules.base import Module
from modules.chat import ChatModule
from modules.exemplo import ExampleModule
from ui import images


def chat_of(app) -> ChatModule:
    return next(m for m in app.modules if isinstance(m, ChatModule))


def example_of(app) -> ExampleModule:
    return next(m for m in app.modules if isinstance(m, ExampleModule))


class Dummy(Module):
    """Módulo mínimo para testar o menu com N cartões (usa a página do exemplo)."""

    def __init__(self, services, n, reason=None):
        super().__init__(services)
        self.id, self.title, self._reason = f"m{n}", f"Atividade {n}", reason
        self.entered = 0

    def unavailable_reason(self):
        return self._reason

    def resource(self, name):
        return ExampleModule.resource(ExampleModule(self.services), name)

    async def enter(self, go_back):
        self.entered += 1
        from modules.exemplo.controller import ExampleController

        return ExampleController(self.title, go_back)

    async def exit(self):
        pass


def dummies(n, **kwargs):
    return lambda services: [Dummy(services, i, **kwargs) for i in range(n)]


def depth(app) -> int:
    return find(app.window, "stack").property("depth")


# ---------- menu ----------


async def test_menu_lista_os_modulos_registrados_na_ordem(make_app):
    app = make_app()
    await pump()
    cards = [i.objectName() for i in find_all(app.window, "card_")]
    assert cards == ["card_chat", "card_exemplo"]
    assert find(app.window, "menuMessage") is None  # sem problema, sem aviso


async def test_problema_de_configuracao_aparece_no_menu(make_app):
    app = make_app(llm_problem="Falta a chave da API: crie config/secrets.toml.")
    await pump()
    message = find(app.window, "menuMessage")
    assert "Falta a chave da API" in label(message)


async def test_um_modulo_vira_cartao_grande_e_centralizado(make_app):
    app = make_app(modules=dummies(1))
    await pump(0.2)
    (card,) = find_all(app.window, "card_")
    assert card.width() >= 420 and card.height() >= 260
    middle = card.mapToScene(card.boundingRect().center())
    assert abs(middle.x() - app.window.width() / 2) < 4


async def test_grade_centralizada_de_ate_tres_colunas(make_app):
    app = make_app(modules=dummies(5))
    await pump(0.2)
    cards = find_all(app.window, "card_")
    rows = sorted({round(c.mapToScene(c.boundingRect().topLeft()).y()) for c in cards})
    assert len(rows) == 2  # 3 + 2
    first_row = [c for c in cards if round(c.mapToScene(c.boundingRect().topLeft()).y()) == rows[0]]
    assert len(first_row) == 3


async def test_muitos_modulos_rolam_com_o_titulo_fixo(make_app):
    app = make_app(modules=dummies(9))
    await pump(0.2)
    scroll = find(app.window, "menuScroll")
    assert scroll.property("interactive") is True
    assert scroll.property("contentHeight") > scroll.height()


async def test_sem_modulos_o_menu_explica(make_app):
    app = make_app(modules=[])
    await pump()
    assert "Nenhum módulo ativo" in label(find(app.window, "menuMessage"))


async def test_cartao_indisponivel_mostra_o_motivo_curto(make_app):
    reason = "Falta a chave da API: crie config/secrets.toml. Veja o README."
    app = make_app(modules=dummies(2, reason=reason))
    await pump()
    assert short_reason(reason) == "Falta a chave da API"
    card = find(app.window, "card_m0")
    assert any("⚠ Falta a chave da API" == label(i) for i in items(app.window) if i.parentItem()
               and _inside(card, i))  # fmt: skip

    click(app.window, card)
    await pump(0.1)
    assert app.active is None
    assert app.modules[0].entered == 0
    assert "Atividade 0: Falta a chave da API" in label(find(app.window, "menuMessage"))


def _inside(ancestor, item) -> bool:
    while item is not None:
        if item is ancestor:
            return True
        item = item.parentItem()
    return False


async def test_abrir_direto_com_um_unico_modulo(make_app):
    app = make_app(modules=dummies(1), open_single_module=True)
    await until(lambda: app.active is not None)
    await pump(0.3)
    assert find(app.window, "examplePage") is not None
    assert depth(app) == 2  # o menu continua embaixo: ← Menu volta para ele

    sozinho_indisponivel = make_app(modules=dummies(1, reason="sem chave"), open_single_module=True)
    await pump(0.1)
    assert sozinho_indisponivel.active is None


# ---------- navegação ----------


async def test_tocar_no_cartao_entra_e_menu_volta(make_app):
    app = make_app()
    await pump()
    chat = chat_of(app)
    click(app.window, find(app.window, "card_chat"))
    await until(lambda: app.active is chat)
    await pump(0.3)
    assert find(app.window, "chatPage") is not None
    recorder = app.services.recorders[-1]
    assert recorder.opened == 1  # microfone aberto (pausado) só dentro do módulo

    click(app.window, find(app.window, "backButton"))  # sem pergunta em edição: sai direto
    await until(lambda: app.active is None)
    await pump(0.3)
    assert depth(app) == 1
    assert find(app.window, "chatPage") is None
    assert recorder.closed == 1
    assert chat.session is None and chat.controller is None


async def test_navegacao_repetida_nao_acumula_recursos(make_app):
    app = make_app()
    chat, example = chat_of(app), example_of(app)
    # Aquecimento: o Qt cria a camada dos popups (QQuickOverlay) uma vez só, no
    # primeiro uso; a contagem de referência é a de depois disso.
    await app.enter_module(chat)
    await pump(0.3)
    await app.leave_module()
    await pump(0.4)
    tarefas_iniciais = len(asyncio.all_tasks())
    itens_no_menu = len(screen_items(app.window))

    for _ in range(5):
        assert await app.enter_module(chat)
        await pump(0.3)
        chat.controller.notice("info", "aviso com timer")
        chat.controller.takePhoto(0)  # foto registrada na memória de imagens
        await pump(0.1)
        await app.leave_module()
        await pump(0.4)
        assert depth(app) == 1
        assert len(screen_items(app.window)) == itens_no_menu
        assert len(asyncio.all_tasks()) <= tarefas_iniciais
        assert images.stored() == 0  # fotos não sobrevivem à saída

        assert await app.enter_module(example)
        await pump(0.3)
        await app.leave_module()
        await pump(0.4)
        assert len(screen_items(app.window)) == itens_no_menu
        assert example.controller is None

    assert len(app.services.recorders) == 6
    assert all(r.opened == 1 and r.closed == 1 for r in app.services.recorders)
    assert app.services.llm.resets == 12  # entrada e saída: conversa nunca sobrevive


async def test_toque_duplo_no_cartao_abre_uma_vez(make_app):
    app = make_app()
    chat = chat_of(app)
    app.open_module(chat)
    app.open_module(chat)
    await until(lambda: app.active is chat)
    await pump(0.3)
    assert len(app.services.recorders) == 1
    assert depth(app) == 2


async def test_encerrar_o_app_libera_o_modulo_e_os_servicos(make_app):
    app = make_app()
    chat = chat_of(app)
    await app.enter_module(chat)
    await pump(0.1)
    recorder = app.services.recorders[-1]

    await app.shutdown()
    await app.shutdown()  # idempotente

    assert recorder.closed == 1
    assert app.services.closed == 1
    assert app.active is None and app.window is None


async def test_falha_ao_abrir_o_modulo_volta_ao_menu_com_aviso(make_app, monkeypatch):
    app = make_app()
    chat = chat_of(app)

    async def quebra(*_a):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat, "enter", quebra)
    assert await app.enter_module(chat) is False
    await pump(0.1)
    assert app.active is None
    assert depth(app) == 1
    assert "Não foi possível abrir" in label(find(app.window, "menuMessage"))


async def test_slot_chamado_depois_da_saida_nao_faz_nada(make_app):
    """A página ainda anima a saída lendo o controller: ele não pode agir mais."""
    app = make_app()
    example = example_of(app)
    await app.enter_module(example)
    controller = app.page
    await app.leave_module()
    assert controller.check("28") is False
    controller.back()  # não chama go_back de novo
    await pump(0.1)
    assert app.active is None


# ---------- módulo de exemplo ----------


async def test_modulo_de_exemplo_valida_calcula_e_volta(make_app):
    app = make_app()
    example = example_of(app)
    await app.enter_module(example)  # aquecimento (ver acima)
    await pump(0.3)
    await app.leave_module()
    await pump(0.4)
    itens_no_menu = len(screen_items(app.window))
    assert await app.enter_module(example)
    await pump(0.3)
    window = app.window
    field = find(window, "numberField")
    assert field.hasActiveFocus()
    hints = int(field.property("inputMethodHints").value)
    assert hints & int(Qt.InputMethodHint.ImhDigitsOnly.value)  # teclado já no numérico

    type_text(window, "abc")
    click(window, find(window, "checkButton"))
    await pump()
    assert label(find(window, "verdict")) == "Entrada inválida"
    assert "só algarismos" in label(find(window, "details"))
    assert field.property("selectedText") == "abc"  # pronto para corrigir

    click(window, find(window, "clearButton"))
    await pump()
    type_text(window, "28")
    key(window, Qt.Key.Key_Return)  # Enter = Verificar
    await pump()
    assert label(find(window, "verdict")) == "28 não é primo: tem 6 divisores."
    assert "28 = 2² × 7" in label(find(window, "details"))

    click(window, find(window, "backButton"))
    await until(lambda: app.active is None)
    await pump(0.4)
    assert example.controller is None
    assert len(screen_items(window)) == itens_no_menu
    assert app.services.recorders == []  # não abriu microfone


# ---------- pré-carregamento do Whisper ----------


async def test_pre_carrega_a_voz_so_se_algum_modulo_usa(make_app):
    app = make_app()  # chat + exemplo
    app._preload_speech()
    assert app.services.preloads == 1

    app = make_app(modules=lambda s: [ExampleModule(s)])
    app._preload_speech()
    assert app.services.preloads == 0

    app = make_app()
    app.services.settings = {"stt": {"preload": False}}
    app._preload_speech()
    assert app.services.preloads == 0


async def test_controller_exposto_a_qml_e_um_qobject(make_app):
    app = make_app()
    await app.enter_module(chat_of(app))
    assert isinstance(app.page, QObject)
