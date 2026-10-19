"""Fixtures dos testes de interface com Qt Quick de verdade (utilitários em qthelpers.py).

Rodam sem servidor gráfico: a plataforma "offscreen" do Qt desenha em memória.
O teclado da tela é o mesmo da aplicação (Qt Virtual Keyboard). Os serviços
são dublês (tests/fakes.py): nada de rede, microfone ou câmera.
"""

import os

# Antes de qualquer QGuiApplication (só nasce na fixture qapp).
if not os.environ.get("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402
from fakes import FakeServices  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from qthelpers import pump  # noqa: E402

from core.app import App, configure_qt  # noqa: E402
from modules import REGISTRY, build_modules  # noqa: E402

configure_qt(on_screen_keyboard=True)


@pytest.fixture(scope="session")
def qapp():
    app = QGuiApplication.instance() or QGuiApplication(["hai-tests"])
    yield app


@pytest.fixture
async def make_app(qapp):
    apps = []

    def factory(modules=None, open_single_module=False, **kwargs):
        services = FakeServices(**kwargs)
        # Por padrão, todos os módulos registrados, ativos ou não: a interface de
        # cada um continua testada mesmo desativada no menu padrão.
        if modules is None:
            modules = build_modules(services, enabled=list(REGISTRY))
        elif callable(modules):
            modules = modules(services)
        app = App(services, modules, fullscreen=False, open_single_module=open_single_module)
        app.build()
        apps.append(app)
        return app

    yield factory
    for app in apps:
        await app.shutdown()
    await pump(0.02)
