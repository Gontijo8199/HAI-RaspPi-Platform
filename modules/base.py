"""
Contrato mínimo de um módulo educacional exibido no menu principal.
Referência mais curta de uma implementação: modules/exemplo/.

Um módulo é uma pasta com:
- module.py: a subclasse de Module (registro no menu e ciclo de vida);
- controller.py: um QObject com o estado e as ações da tela (testável sem QML);
- Page.qml: a tela, que só lê o controller e chama os slots dele;
- icon.svg: o ícone do cartão do menu.

Ciclo de vida (controlado por core/app.py, nunca pelo próprio módulo):

    módulo = ExampleModule(services)          # construção: barata, sem abrir recurso nenhum
    controller = await módulo.enter(voltar)   # toque no cartão: adquire os recursos e
                                              # devolve o controller; a App empilha
                                              # Page.qml com ele como `controller`
    await módulo.exit()                       # voltou ao menu (ou o app está fechando):
                                              # cancela tarefas e libera os recursos;
                                              # a App já tirou a página da pilha
    await módulo.close()                      # app encerrando: libera o que o módulo
                                              # manteve entre entradas (normalmente nada)

Regras:
- enter()/exit() sempre alternam; exit() precisa ser seguro mesmo se enter()
  falhou no meio.
- Serviços caros e compartilhados (LLM, TTS, Whisper, câmera) vêm de
  core.services.Services e NÃO são encerrados pelo módulo.
- O controller não deve fazer nada depois de exit(): timers parados, slots
  ignorados (a página ainda pode estar na animação de saída).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.services import Services


class Module:
    #: Identificador estável (usado em logs e testes).
    id: str = ""
    #: Texto do cartão no menu.
    title: str = ""
    #: Linha curta abaixo do título no cartão (opcional).
    summary: str = ""
    #: Usa reconhecimento de voz: a App pré-carrega o Whisper enquanto o menu está aberto.
    uses_speech: bool = False
    #: Arquivos da pasta do módulo: ícone do cartão e tela.
    icon: str = "icon.svg"
    page: str = "Page.qml"

    def __init__(self, services: Services):
        self.services = services

    def unavailable_reason(self) -> str | None:
        """Motivo legível para o módulo não poder abrir agora (None = pode abrir)."""
        return None

    def resource(self, name: str) -> Path:
        """Arquivo `name` da pasta do módulo."""
        return Path(inspect.getfile(type(self))).parent / name

    async def enter(self, go_back: Callable[[], None]) -> QObject:
        raise NotImplementedError

    async def exit(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        pass
