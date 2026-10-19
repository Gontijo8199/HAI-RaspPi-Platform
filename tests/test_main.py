"""Ponto de entrada (core/main.py) e inicialização (core.app.main)."""

import asyncio
import os

import pytest
from fakes import FakeServices

import core.app
from core.main import parse_args
from modules import enabled_ids


def test_linha_de_comando_so_tem_opcoes_da_interface_grafica():
    args = parse_args(["--windowed", "--no-tts"])
    assert args.windowed and args.no_tts and args.tts_backend is None
    for removida in ("--terminal", "--ptt", "--allow-barge-in"):
        with pytest.raises(SystemExit):
            parse_args([removida])


@pytest.fixture
def fake_main(monkeypatch):
    """main() com configuração vazia e serviços dublês (sem rede, áudio ou câmera)."""
    created = []

    def services(*_args, **_kwargs):
        created.append(FakeServices())
        return created[-1]

    monkeypatch.setattr(core.app, "load_config", lambda: ({}, {}, []))
    monkeypatch.setattr(core.app, "Services", services)
    return created


def test_sem_tela_grafica_retorna_1_e_fecha_os_servicos(fake_main, monkeypatch, capsys):
    monkeypatch.setattr(core.app, "has_display", lambda: False)
    assert core.app.main(windowed=True) == 1
    assert fake_main[0].closed == 1
    assert "sessão gráfica" in capsys.readouterr().err


def test_inicia_mostra_o_menu_e_encerra_limpo(fake_main, monkeypatch, qapp):
    seen = {}
    original_build = core.app.App.build

    def build_and_schedule_stop(self):
        original_build(self)
        seen["cards"] = [c["id"] for c in self.controller.modules]
        seen["fullscreen"] = self.controller.fullscreen
        asyncio.get_running_loop().call_later(0.2, self.request_stop)

    monkeypatch.setattr(core.app.App, "build", build_and_schedule_stop)
    assert core.app.main(windowed=True) == 0
    assert seen["cards"] == enabled_ids()  # só os ativos por padrão
    assert seen["fullscreen"] is False  # --windowed vence o padrão de tela cheia
    assert fake_main[0].closed == 1


def test_teclado_da_tela_vira_o_metodo_de_entrada(monkeypatch):
    """A sessão (GNOME, por exemplo) exporta QT_IM_MODULES=ibus: sem sobrescrever
    as duas variáveis, o Qt carrega o IBus e o teclado da tela nunca aparece."""
    monkeypatch.setenv("QT_IM_MODULE", "ibus")
    monkeypatch.setenv("QT_IM_MODULES", "wayland;ibus")
    core.app.configure_qt(on_screen_keyboard=True)
    assert os.environ["QT_IM_MODULE"] == os.environ["QT_IM_MODULES"] == "qtvirtualkeyboard"


def test_sem_teclado_da_tela_fica_o_metodo_do_sistema(monkeypatch):
    monkeypatch.setenv("QT_IM_MODULE", "ibus")
    monkeypatch.setenv("QT_IM_MODULES", "wayland;ibus")
    core.app.configure_qt(on_screen_keyboard=False)
    assert os.environ["QT_IM_MODULE"] == "ibus"
    assert os.environ["QT_IM_MODULES"] == "wayland;ibus"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"QT_QPA_PLATFORM": "offscreen"}, True),
        ({"QT_QPA_PLATFORM": "eglfs"}, True),
        ({"WAYLAND_DISPLAY": "wayland-0"}, True),
        ({"DISPLAY": ":0"}, True),
        ({}, False),
        ({"QT_QPA_PLATFORM": "wayland"}, False),
    ],
)
def test_detecta_se_ha_tela(monkeypatch, env, expected):
    for name in ("QT_QPA_PLATFORM", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert core.app.has_display() is expected
