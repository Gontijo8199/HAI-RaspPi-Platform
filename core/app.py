"""
Aplicação gráfica: configuração, janela, menu principal, navegação e ciclo de
vida dos módulos. main() é chamado por core/main.py.

Modelo de execução:
- Um único event loop: o do Qt, que também roda o asyncio (qasync). Os slots
  chamados pela QML rodam na mesma thread das tarefas assíncronas - nenhuma
  fila entre threads.
- A tela é Qt Quick (QML, desenhada pela GPU). Ela só lê o estado dos
  controllers e chama os slots deles; quem decide é o Python.
- Trabalho pesado (rede, Whisper, câmera, áudio) continua fora do loop, nas
  threads que cada serviço já usa; a interface nunca trava durante eles.

Navegação:
- O menu fica sempre na base da pilha de telas (StackView em Main.qml).
- Cada entrada num módulo: module.enter() devolve o controller, e a App
  empilha a Page.qml do módulo com ele. Na saída a página sai da pilha e o
  módulo libera seus recursos (exit).
- Abrir/voltar passam por um lock: toques repetidos não abrem duas vezes.

Teclado da tela: o Qt Virtual Keyboard, como método de entrada do próprio
processo ([display] on_screen_keyboard). Sem ele, vale o do sistema.

Encerramento (fechar a janela, Ctrl+C, SIGTERM): sai do módulo ativo,
chama close() de cada módulo e Services.close(), e só então fecha a janela.

Falhas: exceção num slot vai para o log (a tela continua); falha ao abrir um
módulo volta ao menu com aviso; sem tela gráfica, main() retorna 1.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Coroutine

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from core.services import Services, load_config
from modules import build_modules
from modules.base import Module
from ui import QML_DIR, images, theme

logger = logging.getLogger(__name__)

# Whisper pré-carregado pouco depois do menu aparecer: o import e o load (em
# thread) disputam o GIL com a interface, melhor no menu do que na conversa.
_PRELOAD_DELAY_S = 1.0
# Sem add_signal_handler, o Python só trata o Ctrl+C quando volta a rodar
# código: um timer curto garante isso com o Qt parado no event loop.
_SIGNAL_POLL_MS = 250


def short_reason(reason: str) -> str:
    """Primeira frase do motivo, sem o detalhe depois de ':' (cabe no cartão)."""
    return reason.split(":")[0].split(". ")[0].rstrip(".")


def configure_qt(on_screen_keyboard: bool) -> None:
    """Ambiente do Qt. Precisa rodar antes de criar a QGuiApplication.

    O teclado da tela é o método de entrada do processo. A sessão do sistema
    costuma exportar QT_IM_MODULES=ibus (GNOME) ou outro: sem sobrescrever
    as duas variáveis, o Qt carrega o do sistema e o teclado nunca aparece.
    """
    if on_screen_keyboard:
        os.environ["QT_IM_MODULE"] = "qtvirtualkeyboard"
        os.environ["QT_IM_MODULES"] = "qtvirtualkeyboard"
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")


def has_display() -> bool:
    """Há onde abrir a janela? Sem isso o Qt aborta o processo ao iniciar."""
    platform = os.environ.get("QT_QPA_PLATFORM", "")
    if platform and not platform.startswith(("wayland", "xcb")):
        return True  # offscreen, eglfs, linuxfb: não dependem de sessão gráfica
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


class DisplayUnavailable(RuntimeError):
    """Não há tela gráfica, ou a interface não carregou."""


class AppController(QObject):
    """O que Main.qml e MenuPage.qml enxergam como `app`."""

    pagePushed = Signal(str, QObject)
    pagePopped = Signal()
    menuMessageChanged = Signal()
    fullscreenChanged = Signal()
    keyboardEnabledChanged = Signal()

    def __init__(self, app: App, cards: list[dict], *, fullscreen: bool, size: tuple[int, int]):
        super().__init__()
        self._app = app
        self._cards = cards
        self._fullscreen = fullscreen
        self._size = size
        self._message = ""
        self._keyboard_enabled = app.services.on_screen_keyboard

    def _get_modules(self) -> list:
        return self._cards

    def _get_message(self) -> str:
        return self._message

    def _get_fullscreen(self) -> bool:
        return self._fullscreen

    def _set_fullscreen(self, value: bool) -> None:
        if value != self._fullscreen:
            self._fullscreen = value
            self.fullscreenChanged.emit()

    def _get_keyboard(self) -> bool:
        return self._app.services.on_screen_keyboard

    def _get_keyboard_enabled(self) -> bool:
        return self._keyboard_enabled

    def _set_keyboard_enabled(self, value: bool) -> None:
        if value != self._keyboard_enabled:
            self._keyboard_enabled = value
            self.keyboardEnabledChanged.emit()

    def _get_width(self) -> int:
        return self._size[0]

    def _get_height(self) -> int:
        return self._size[1]

    modules = Property("QVariantList", _get_modules, constant=True)
    menuMessage = Property(str, _get_message, notify=menuMessageChanged)
    fullscreen = Property(bool, _get_fullscreen, _set_fullscreen, notify=fullscreenChanged)
    #: o teclado da tela está instalado ([display] on_screen_keyboard)
    onScreenKeyboard = Property(bool, _get_keyboard, constant=True)
    #: e o aluno quer que ele apareça (menu ⋯ "Teclado na tela"; vale até fechar o app)
    keyboardEnabled = Property(
        bool, _get_keyboard_enabled, _set_keyboard_enabled, notify=keyboardEnabledChanged
    )
    windowWidth = Property(int, _get_width, constant=True)
    windowHeight = Property(int, _get_height, constant=True)

    def set_message(self, text: str) -> None:
        if text != self._message:
            self._message = text
            self.menuMessageChanged.emit()

    @Slot(str)
    def open(self, module_id: str) -> None:
        module = next((m for m in self._app.modules if m.id == module_id), None)
        if module is not None:
            self._app.open_module(module)

    @Slot()
    def back(self) -> None:
        self._app.back_to_menu()

    @Slot()
    def quit(self) -> None:
        self._app.request_stop()


class App:
    """Janela principal com menu e módulos.

    Parâmetros
    ----------
    services : Services
        Serviços compartilhados (encerrados no shutdown).
    modules : list[Module]
        Módulos do menu, na ordem de exibição.
    fullscreen, width, height
        Geometria da janela.
    open_single_module : bool
        Com um só módulo ativo (e disponível), abre-o direto ao iniciar.
        Voltar ainda leva ao menu.
    """

    def __init__(
        self,
        services: Services,
        modules: list[Module],
        *,
        fullscreen: bool = True,
        width: int = 1024,
        height: int = 600,
        open_single_module: bool = False,
    ):
        self.services = services
        self.modules = modules
        self._open_single = open_single_module
        self._geometry = (fullscreen, width, height)
        self.engine: QQmlApplicationEngine | None = None
        self.window: QObject | None = None
        self.controller: AppController | None = None
        self.active: Module | None = None
        self.page: QObject | None = None  # controller do módulo aberto
        self._retired: QObject | None = None  # controller da página em animação de saída
        self._nav_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._stop = asyncio.Event()
        self._closed = False

    # ------------------------------------------------------------------ execução

    def build(self) -> None:
        """Cria a janela e o menu. Chamado por run(); útil em testes.

        Precisa de uma QGuiApplication já criada (main() ou os testes).
        """
        if QGuiApplication.instance() is None:
            raise DisplayUnavailable("QGuiApplication não foi criada.")
        fullscreen, width, height = self._geometry
        self.controller = AppController(
            self, self._cards(), fullscreen=fullscreen, size=(width, height)
        )
        engine = QQmlApplicationEngine()
        engine.addImportPath(str(QML_DIR))
        engine.addImageProvider(images.PROVIDER, images.ImageStore())
        engine.rootContext().setContextProperty("theme", theme.as_qml())
        engine.rootContext().setContextProperty("app", self.controller)
        engine.warnings.connect(_log_qml_warnings)
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
        if not engine.rootObjects():
            raise DisplayUnavailable("a interface (ui/qml/Main.qml) não carregou; veja o log.")
        self.engine = engine
        self.window = engine.rootObjects()[0]

        problems = [*self.services.config_problems]
        if self.services.llm_problem:
            problems.append(self.services.llm_problem)
        if not self.modules:
            problems.append("Nenhum módulo ativo: confira [modules] em config/settings.toml.")
        self.controller.set_message("\n".join(problems))
        if self._open_single and len(self.modules) == 1:
            (only,) = self.modules
            if only.unavailable_reason() is None:
                self.open_module(only)

    async def run(self) -> None:
        self.build()
        loop = asyncio.get_running_loop()
        preload = loop.call_later(_PRELOAD_DELAY_S, self._preload_speech)
        poll = self._install_signal_handlers(loop)
        try:
            await self._stop.wait()
        finally:
            preload.cancel()
            if poll is not None:
                poll.stop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                    loop.remove_signal_handler(sig)
            await self.shutdown()

    def _install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> QTimer | None:
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self.request_stop)
            return None
        except (NotImplementedError, RuntimeError, ValueError):
            pass
        with contextlib.suppress(ValueError):  # fora da thread principal (testes)
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: self.request_stop())
        poll = QTimer()
        poll.timeout.connect(lambda: None)
        poll.start(_SIGNAL_POLL_MS)
        return poll

    def _preload_speech(self) -> None:
        """Carrega o Whisper em segundo plano se algum módulo usa voz
        ([stt] preload = false desliga)."""
        if self._closed or not any(getattr(m, "uses_speech", False) for m in self.modules):
            return
        if not self.services.settings.get("stt", {}).get("preload", True):
            return
        self.services.preload_asr()

    def request_stop(self) -> None:
        self._stop.set()

    async def shutdown(self) -> None:
        """Sai do módulo ativo, fecha módulos e serviços, fecha a janela. Idempotente."""
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
        if self.window is not None:
            self.window.setProperty("visible", False)
        # O motor (e a janela) morre aqui, antes dos objetos que a QML lê
        # (controller da App e dos módulos): sem isso as bindings avaliam null.
        engine, self.engine, self.window = self.engine, None, None
        del engine
        self._retired = None
        logger.info("Aplicação encerrada.")

    # ------------------------------------------------------------------ navegação

    def open_module(self, module: Module) -> None:
        """Toque num cartão do menu."""
        self._spawn(self.enter_module(module))

    def back_to_menu(self) -> None:
        """Botão ← Menu de um módulo."""
        self._spawn(self.leave_module())

    async def enter_module(self, module: Module) -> bool:
        async with self._nav_lock:
            if self._closed or self.active is not None:
                return False
            reason = module.unavailable_reason()
            if reason:
                self.controller.set_message(f"{module.title}: {reason}")
                return False
            self.active = module
            try:
                page = await module.enter(self.back_to_menu)
            except Exception:
                logger.exception("Falha ao abrir o módulo %s.", module.id)
                await self._leave_active()
                self.controller.set_message(
                    f"Não foi possível abrir “{module.title}”. Os detalhes estão no log."
                )
                return False
            self.page = page
            self._retired = None
            url = QUrl.fromLocalFile(str(module.resource(module.page))).toString()
            self.controller.pagePushed.emit(url, page)
            logger.info("Módulo aberto: %s", module.id)
            return True

    async def leave_module(self) -> None:
        async with self._nav_lock:
            await self._leave_active()

    async def _leave_active(self) -> None:
        module, page = self.active, self.page
        self.active, self.page = None, None
        if page is not None and self.controller is not None:
            self.controller.pagePopped.emit()
            # A página ainda anima a saída lendo o controller: ele vive até a
            # próxima navegação.
            self._retired = page
        if module is not None:
            try:
                await module.exit()
            except Exception:
                logger.exception("Erro ao sair do módulo %s.", module.id)
            logger.info("Módulo fechado: %s", module.id)

    def _cards(self) -> list[dict]:
        cards = []
        for module in self.modules:
            reason = module.unavailable_reason()
            icon = module.resource(module.icon)
            cards.append(
                {
                    "id": module.id,
                    "title": module.title,
                    "summary": module.summary,
                    "icon": QUrl.fromLocalFile(str(icon)).toString() if icon.exists() else "",
                    "reason": reason or "",
                    "shortReason": short_reason(reason) if reason else "",
                }
            )
        return cards

    def _spawn(self, coro: Coroutine) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _log_qml_warnings(warnings) -> None:
    for warning in warnings:
        logger.warning("QML: %s", warning.toString())


def main(*, windowed: bool = False, tts_backend: str | None = None, no_tts: bool = False) -> int:
    """Carrega a configuração, cria os serviços e roda a aplicação até ela fechar.

    Retorna o código de saída do processo (1 = sem tela gráfica).
    """
    import qasync

    settings, secrets, problems = load_config()
    for problem in problems:
        logger.warning(problem)
    services = Services(
        settings, secrets, tts_backend=tts_backend, no_tts=no_tts, config_problems=problems
    )
    configure_qt(services.on_screen_keyboard)
    if not has_display():
        services.close()
        logger.error("Sem tela gráfica ($WAYLAND_DISPLAY e $DISPLAY vazios).")
        print(
            "Não foi possível abrir a interface gráfica: não há sessão gráfica\n"
            "($WAYLAND_DISPLAY ou $DISPLAY). Veja a seção Execução do README.",
            file=sys.stderr,
        )
        return 1
    qt_app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    qt_app.setApplicationName("HAI")
    qt_app.setDesktopFileName("hai")
    display_cfg = settings.get("display", {})
    app = App(
        services,
        build_modules(services),
        fullscreen=display_cfg.get("fullscreen", True) and not windowed,
        width=display_cfg.get("width", 1024),
        height=display_cfg.get("height", 600),
        open_single_module=bool(display_cfg.get("open_single_module", False)),
    )
    try:
        qasync.run(app.run())
    except DisplayUnavailable as exc:
        services.close()
        logger.error("Interface indisponível: %s", exc)
        print(f"Não foi possível abrir a interface gráfica ({exc}).", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0
