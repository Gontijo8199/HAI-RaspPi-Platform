"""
Módulos educacionais disponíveis no menu principal.

Para adicionar um módulo: crie modules/<nome>/ com uma subclasse de
modules.base.Module e inclua-a em build_modules() — o menu é montado a partir
desta lista, na ordem dela.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.base import Module

if TYPE_CHECKING:
    from core.services import Services


def build_modules(services: Services) -> list[Module]:
    from modules.chat import ChatModule

    return [ChatModule(services)]


__all__ = ["Module", "build_modules"]
