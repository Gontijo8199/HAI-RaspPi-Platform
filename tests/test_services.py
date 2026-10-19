"""Configuração e serviços compartilhados (core/services.py)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from core.services import NullTTS, Services, SpeechUnavailable, build_llm, load_config


def test_load_config_sem_arquivos_nao_quebra(tmp_path):
    settings, secrets, problems = load_config(tmp_path / "a.toml", tmp_path / "b.toml")
    assert settings == {} and secrets == {}
    assert len(problems) == 2
    assert "settings.example.toml" in problems[0]


def test_load_config_toml_invalido_vira_problema(tmp_path):
    (tmp_path / "s.toml").write_text("[api\nmodel=")
    (tmp_path / "k.toml").write_text('[api]\nkey = "x"\n')
    _settings, secrets, problems = load_config(tmp_path / "s.toml", tmp_path / "k.toml")
    assert secrets == {"api": {"key": "x"}}
    assert "formatação" in problems[0]


def test_build_llm_sem_chave_explica_o_problema():
    client, problem = build_llm({}, {})
    assert client is None
    assert "secrets.toml" in problem


@patch("google.genai.Client")
def test_build_llm_usa_o_modelo_configurado(_mock_genai):
    client, problem = build_llm({"api": {"model": "modelo-x"}}, {"api": {"key": "k"}})
    assert problem is None and client.model == "modelo-x"


def _services(**kw):
    return Services({"camera": {"enabled": False}}, {}, no_tts=True, **kw)


def test_services_sem_chave_e_sem_tts():
    services = _services(config_problems=["faltou algo"])
    assert services.llm is None and services.llm_problem
    assert isinstance(services.tts, NullTTS)
    assert services.voice_output_available is False
    assert services.camera is None
    services.close()


async def test_whisper_e_carregado_uma_vez_e_compartilhado():
    services = _services()
    engine = MagicMock()
    with patch.object(Services, "_load_asr", return_value=engine) as load:
        a, b = await asyncio.gather(services.get_asr(), services.get_asr())
        c = await services.get_asr()
    assert a is b is c is engine
    load.assert_called_once()


async def test_falha_do_whisper_e_legivel_e_permite_tentar_de_novo():
    services = _services()
    with patch.object(Services, "_load_asr", side_effect=[OSError("sem rede"), "ok"]):
        with pytest.raises(SpeechUnavailable):
            await services.get_asr()
        assert await services.get_asr() == "ok"


async def test_cancelar_quem_espera_nao_cancela_o_carregamento():
    services = _services()
    import threading

    liberar = threading.Event()

    def lento():
        liberar.wait(2)
        return "engine"

    with patch.object(Services, "_load_asr", side_effect=lento):
        espera = asyncio.create_task(services.get_asr())
        await asyncio.sleep(0.01)
        espera.cancel()
        with pytest.raises(asyncio.CancelledError):
            await espera
        liberar.set()
        assert await services.get_asr() == "engine"


def test_teclado_na_tela_vem_ligado_por_padrao_e_pode_ser_desligado():
    assert _services().on_screen_keyboard is True
    services = Services(
        {"camera": {"enabled": False}, "display": {"on_screen_keyboard": False}}, {}, no_tts=True
    )
    assert services.on_screen_keyboard is False


def test_caminhos_do_piper_vem_do_ambiente_quando_o_settings_nao_define(monkeypatch):
    from core.services import build_tts

    monkeypatch.setenv("PIPER_BIN", "/opt/piper/piper/piper")
    monkeypatch.setenv("PIPER_MODEL", "/opt/piper/voices/voz.onnx")
    with patch("core.services.TTSSpeaker") as speaker:
        build_tts({"tts": {"backend": "piper"}}, None, False)
        build_tts({"tts": {"piper_bin": "/meu/piper"}}, None, False)
    first, second = speaker.call_args_list
    assert first.kwargs["piper_bin"] == "/opt/piper/piper/piper"
    assert first.kwargs["piper_model"] == "/opt/piper/voices/voz.onnx"
    assert second.kwargs["piper_bin"] == "/meu/piper"  # settings.toml tem prioridade


async def test_preload_carrega_uma_vez_em_segundo_plano():
    services = _services()
    engine = MagicMock()
    with patch.object(Services, "_load_asr", return_value=engine) as load:
        services.preload_asr()
        services.preload_asr()  # idempotente
        assert await services.get_asr() is engine  # quem chega depois reaproveita
    load.assert_called_once()


async def test_falha_no_preload_nao_vaza_excecao_e_permite_tentar_de_novo():
    services = _services()
    with patch.object(Services, "_load_asr", side_effect=[OSError("sem rede"), "ok"]):
        services.preload_asr()
        await asyncio.sleep(0.05)
        assert services._preload_task.done() and services._preload_task.exception() is None
        assert await services.get_asr() == "ok"
