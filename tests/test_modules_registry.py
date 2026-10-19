"""Registro de módulos (modules/__init__.py): ativar e desativar sem tocar no app."""

import logging

from fakes import FakeServices

from modules import REGISTRY, build_modules, enabled_ids


def ids(modules):
    return [m.id for m in modules]


def test_registro_tem_ids_coerentes_com_as_classes():
    services = FakeServices()
    assert ids(build_modules(services, enabled=list(REGISTRY))) == list(REGISTRY)


def test_padrao_usa_o_estado_do_registro():
    esperados = [mid for mid, (_f, ativo) in REGISTRY.items() if ativo]
    assert enabled_ids() == esperados
    assert ids(build_modules(FakeServices())) == esperados


def test_settings_ativa_e_desativa_modulos():
    services = FakeServices()
    services.settings = {"modules": {"exemplo": True, "chat": False}}
    assert ids(build_modules(services)) == ["exemplo"]


def test_selecao_explicita_mantem_a_ordem_do_registro():
    assert ids(build_modules(FakeServices(), enabled=["exemplo", "chat"])) == ["chat", "exemplo"]


def test_id_desconhecido_no_settings_e_ignorado_com_aviso(caplog):
    with caplog.at_level(logging.WARNING):
        assert "nao-existe" not in enabled_ids({"modules": {"nao-existe": True}})
    assert "nao-existe" in caplog.text


def test_nenhum_modulo_ativo():
    assert build_modules(FakeServices(), enabled=[]) == []
