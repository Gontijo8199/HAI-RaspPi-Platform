"""
Contrato mínimo de um módulo educacional exibido no menu principal.

Ciclo de vida (controlado por core/app.py, nunca pelo próprio módulo):

    módulo = ChatModule(services)    # construção: barata, sem abrir recurso nenhum
    await módulo.enter(frame, voltar)  # usuário tocou no cartão: monta a tela e
                                       # adquire os recursos da atividade
    await módulo.exit()                # voltou ao menu (ou o app está fechando):
                                       # cancela tarefas e libera os recursos da
                                       # atividade; o frame é destruído pelo app
    await módulo.close()               # app encerrando: libera o que o módulo
                                       # manteve entre entradas (normalmente nada)

Regras:
- enter()/exit() sempre alternam; exit() precisa ser seguro mesmo se enter()
  falhou no meio.
- Serviços caros e compartilhados (LLM, TTS, Whisper, câmera) vêm de
  core.services.Services e NÃO são encerrados pelo módulo.
- Os widgets criados dentro do frame são destruídos junto com ele, então
  binds de widget não se acumulam entre entradas. Binds globais (bind_all) e
  timers (after) precisam ser desfeitos em exit().
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services import Services


class Module:
    #: Identificador estável (usado em logs e testes).
    id: str = ""
    #: Texto do cartão no menu.
    title: str = ""

    def __init__(self, services: Services):
        self.services = services

    def unavailable_reason(self) -> str | None:
        """Motivo legível para o módulo não poder abrir agora (None = pode abrir)."""
        return None

    def draw_icon(self, canvas: tk.Canvas, size: int) -> None:
        """Desenha o ícone do cartão do menu (Canvas size×size, já com o fundo)."""

    async def enter(self, parent: tk.Frame, go_back: Callable[[], None]) -> None:
        raise NotImplementedError

    async def exit(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        pass
