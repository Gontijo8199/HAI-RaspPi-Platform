"""
Aplicação gráfica: janela, menu principal, navegação e ciclo de vida dos módulos.

Modelo de execução:
- Um único event loop asyncio (o mesmo do resto do projeto). O Tk roda NELE:
  run() chama root.update() a cada quadro e cede o loop com asyncio.sleep().
  Assim os callbacks de botão rodam na mesma thread das tarefas assíncronas —
  nenhuma fila entre threads, e um callback nunca toca num widget já
  destruído por outra thread.
- Trabalho pesado (rede, Whisper, câmera, áudio) continua fora do loop, nas
  threads que cada serviço já usa; a interface nunca trava durante eles.

Navegação:
- O menu é construído uma vez e só é escondido/mostrado.
- Cada entrada num módulo ganha um frame novo; na saída o módulo libera seus
  recursos (exit) e o frame é destruído — os widgets e binds vão junto.
- Abrir/voltar passam por um lock: toques repetidos não abrem duas vezes.

Encerramento (fechar a janela, Ctrl+C, SIGTERM): sai do módulo ativo,
chama close() de cada módulo e Services.close(), e só então destrói a janela.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import tkinter as tk
from collections.abc import Coroutine

from core.services import Services
from gui import theme
from gui.menu import MenuScreen
from modules.base import Module

logger = logging.getLogger(__name__)

_FRAME_S = 1 / 50  # ~50 quadros/s: toque responsivo sem pesar na CPU do Pi


class DisplayUnavailable(RuntimeError):
    """Não há tela gráfica (sem $DISPLAY ou sem tkinter)."""


def create_root(fullscreen: bool, width: int, height: int) -> tk.Tk:
    try:
        root = tk.Tk(className="HAI")
    except tk.TclError as exc:
        raise DisplayUnavailable(str(exc)) from exc
    root.title("HAI — IA na Educação")
    root.configure(bg=theme.BG)
    root.minsize(640, 400)
    if fullscreen:
        root.attributes("-fullscreen", True)
    else:
        root.geometry(f"{width}x{height}")
    # Esc sai da tela cheia (como no display do modo terminal).
    root.bind("<Escape>", lambda _e: root.attributes("-fullscreen", False))
    return root


class App:
    """Janela principal com menu e módulos.

    Parâmetros
    ----------
    services : Services
        Serviços compartilhados (encerrados no shutdown).
    modules : list[Module]
        Módulos do menu, na ordem de exibição.
    root : tk.Tk | None
        Janela já criada (testes). Sem ela, run() cria uma com create_root().
    fullscreen, width, height
        Geometria da janela criada por run().
    """

    def __init__(
        self,
        services: Services,
        modules: list[Module],
        *,
        root: tk.Tk | None = None,
        fullscreen: bool = True,
        width: int = 1024,
        height: int = 600,
    ):
        self.services = services
        self.modules = modules
        self.root = root
        self._owns_root = root is None
        self._geometry = (fullscreen, width, height)
        self.menu: MenuScreen | None = None
        self.active: Module | None = None
        self._active_frame: tk.Frame | None = None
        self._container: tk.Frame | None = None
        self._nav_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._stop = asyncio.Event()
        self._closed = False

    # ------------------------------------------------------------------ execução

    def build(self) -> None:
        """Cria a janela (se preciso) e o menu. Chamado por run(); útil em testes."""
        if self.root is None:
            self.root = create_root(*self._geometry)
        self.root.protocol("WM_DELETE_WINDOW", self.request_stop)
        self._fonts = theme.fonts_for(self.root)
        self._container = tk.Frame(self.root, bg=theme.BG)
        self._container.pack(fill="both", expand=True)
        self.menu = MenuScreen(self._container, self.modules, self._fonts, self.open_module)
        self.menu.show()
        problems = [*self.services.config_problems]
        if self.services.llm_problem:
            problems.append(self.services.llm_problem)
        if problems:
            self.menu.show_message("\n".join(problems))

    async def run(self) -> None:
        self.build()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.add_signal_handler(sig, self.request_stop)
        try:
            while not self._stop.is_set():
                try:
                    self.root.update()
                except tk.TclError:
                    break  # janela destruída por fora
                await asyncio.sleep(_FRAME_S)
        finally:
            for sig in (signal.SIGINT, signal.SIGTERM):
                with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                    loop.remove_signal_handler(sig)
            await self.shutdown()

    def request_stop(self) -> None:
        self._stop.set()

    async def shutdown(self) -> None:
        """Sai do módulo ativo, fecha módulos e serviços, destrói a janela. Idempotente."""
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        async with self._nav_lock:
            await self._leave_active()
        for module in self.modules:
            try:
                await module.close()
            except Exception:
                logger.exception("Erro ao encerrar o módulo %s.", module.id)
        self.services.close()
        if self._owns_root and self.root is not None:
            with contextlib.suppress(tk.TclError):
                self.root.destroy()
        logger.info("Aplicação encerrada.")

    # ------------------------------------------------------------------ navegação

    def open_module(self, module: Module) -> None:
        """Toque num cartão do menu."""
        self._spawn(self.enter_module(module))

    def back_to_menu(self) -> None:
        """Botão Voltar de um módulo."""
        self._spawn(self.leave_module())

    async def enter_module(self, module: Module) -> bool:
        async with self._nav_lock:
            if self._closed or self.active is not None:
                return False
            reason = module.unavailable_reason()
            if reason:
                self.menu.show_message(f"{module.title}: {reason}")
                return False
            self.menu.hide()
            frame = tk.Frame(self._container, bg=theme.BG)
            frame.pack(fill="both", expand=True)
            self.active, self._active_frame = module, frame
            try:
                await module.enter(frame, self.back_to_menu)
            except Exception:
                logger.exception("Falha ao abrir o módulo %s.", module.id)
                await self._leave_active()
                self.menu.show_message(
                    f"Não foi possível abrir “{module.title}”. Veja o terminal para detalhes."
                )
                return False
            logger.info("Módulo aberto: %s", module.id)
            return True

    async def leave_module(self) -> None:
        async with self._nav_lock:
            await self._leave_active()

    async def _leave_active(self) -> None:
        module, frame = self.active, self._active_frame
        self.active, self._active_frame = None, None
        if module is not None:
            try:
                await module.exit()
            except Exception:
                logger.exception("Erro ao sair do módulo %s.", module.id)
            logger.info("Módulo fechado: %s", module.id)
        if frame is not None:
            with contextlib.suppress(tk.TclError):
                frame.destroy()
        if self.menu is not None and not self._closed:
            self.menu.show()

    def _spawn(self, coro: Coroutine) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
