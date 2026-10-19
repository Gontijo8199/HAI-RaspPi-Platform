"""
Módulo de exemplo: referência mínima de um módulo da plataforma.

Mostra o contrato de modules/base.py sem nada além do necessário:
- logic.py: regra da atividade, sem interface (testável sozinha);
- controller.py: estado e ações da tela, que só chamam a lógica;
- Page.qml: a tela; icon.svg: o ícone do cartão;
- este arquivo: registro (id, título) e ciclo de vida.

Recursos: o controller é o único recurso por entrada. enter() o cria e
exit() o desliga. Nenhum serviço compartilhado é usado, então o módulo abre
mesmo sem chave da API, câmera ou microfone.
"""

from __future__ import annotations

from collections.abc import Callable

from modules.base import Module
from modules.exemplo.controller import ExampleController


class ExampleModule(Module):
    id = "exemplo"
    title = "Módulo de exemplo"
    summary = "Divisores e números primos"

    def __init__(self, services):
        super().__init__(services)
        self.controller: ExampleController | None = None

    async def enter(self, go_back: Callable[[], None]) -> ExampleController:
        self.controller = ExampleController(self.title, go_back)
        return self.controller

    async def exit(self) -> None:
        if self.controller is not None:
            self.controller.close()
        self.controller = None
