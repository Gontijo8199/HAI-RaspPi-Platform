"""
Módulos educacionais disponíveis no menu principal.

REGISTRY lista todos os módulos, na ordem do menu, com o estado padrão
(ativo ou não). Para ativar ou desativar um módulo:

- no código, troque o booleano em REGISTRY (vale para todas as instalações);
- numa instalação, use [modules] no config/settings.toml, que tem prioridade:

      [modules]
      exemplo = true

Para adicionar um módulo: crie modules/<nome>/ com uma subclasse de
modules.base.Module e inclua uma entrada em REGISTRY. Passo a passo em
docs/development.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from modules.base import Module

if TYPE_CHECKING:
    from core.services import Services

logger = logging.getLogger(__name__)


# Imports dentro das fábricas: um módulo desativado não carrega suas dependências.
def _chat(services: Services) -> Module:
    from modules.chat import ChatModule

    return ChatModule(services)


def _exemplo(services: Services) -> Module:
    from modules.exemplo import ExampleModule

    return ExampleModule(services)


#: id → (fábrica, ativo por padrão). A ordem é a ordem do menu.
REGISTRY: dict[str, tuple[Callable[[Services], Module], bool]] = {
    "chat": (_chat, True),
    "exemplo": (_exemplo, False),
}


def enabled_ids(settings: dict | None = None) -> list[str]:
    """Ids ativos: o padrão de REGISTRY, sobrescrito por [modules] do settings."""
    overrides = (settings or {}).get("modules", {})
    for unknown in set(overrides) - set(REGISTRY):
        logger.warning("[modules] %s: módulo desconhecido, ignorado.", unknown)
    return [
        module_id
        for module_id, (_factory, default) in REGISTRY.items()
        if bool(overrides.get(module_id, default))
    ]


def build_modules(services: Services, enabled: Iterable[str] | None = None) -> list[Module]:
    """Instancia os módulos ativos, na ordem de REGISTRY.

    `enabled` substitui a seleção (testes usam list(REGISTRY) para montar todos);
    sem ele, vale enabled_ids() com o settings dos serviços.
    """
    if enabled is None:
        enabled = enabled_ids(getattr(services, "settings", None))
    wanted = set(enabled)
    return [
        factory(services) for module_id, (factory, _) in REGISTRY.items() if module_id in wanted
    ]


__all__ = ["REGISTRY", "Module", "build_modules", "enabled_ids"]
