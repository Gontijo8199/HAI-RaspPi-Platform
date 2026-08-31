"""
Teclas de controle do terminal (cancelar = Espaço por padrão,
Ctrl+C = sair, Enter = PTT; configurável via [ux] cancel_key).

Design (mesmo padrão de tts/speaker.py e display/markdown_display.py):
- Thread daemon coloca o stdin em modo cbreak (termios) e lê bytes brutos,
  empurrando teclas normalizadas numa asyncio.Queue via call_soon_threadsafe —
  nunca bloqueia o event loop.
- O modo cbreak mantém ISIG ativo: Ctrl+C continua gerando SIGINT normally;
  também é reportado como tecla "ctrl+c" para desligamento elegante.
- Se stdin não for um TTY (CI, pytest, docker sem -it), available == False:
  start() é no-op e get_key() aguarda para sempre — o resto do programa
  funciona normalmente, só sem hotkeys. Nada lança exceção.
- A configuração original do terminal é restaurada em stop() e num
  atexit.register de segurança, mesmo após crashes.

Sequências de escape são resolvidas com select(): um Esc puro chega como
byte isolado; setas/chegam como b"\\x1b[A" etc. e são mapeados em nomes.
"""

import asyncio
import atexit
import logging
import os
import select
import sys
import termios
import threading
import tty

logger = logging.getLogger(__name__)

_ESCAPE_WAIT_S = 0.01  # janela para agrupar bytes de uma sequência \x1b[..

_KEY_NAMES = {
    b"\x1b[A": "up",
    b"\x1b[B": "down",
    b"\x1b[C": "right",
    b"\x1b[D": "left",
    b"\x1b[H": "home",
    b"\x1b[F": "end",
}

_CTRL_KEYS = {
    3: "ctrl+c",
    4: "ctrl+d",
    26: "ctrl+z",
}

# Nomes aceitos na configuração ([ux] cancel_key) e como exibir ao usuário.
_KEY_ALIASES = {
    "space": "space",
    "espaco": "space",
    "espaço": "space",
    "esc": "esc",
    "escape": "esc",
    "enter": "enter",
    "tab": "tab",
    "backspace": "backspace",
    "ctrl+c": "ctrl+c",
}

_PRETTY_NAMES = {
    "space": "Espaço",
    "esc": "Esc",
    "enter": "Enter",
    "tab": "Tab",
    "backspace": "Backspace",
    "ctrl+c": "Ctrl+C",
}


def parse_key(name: str) -> str:
    """Converte um nome de tecla legível no token canônico usado internamente.

    Aceita apelidos ('space', 'espaco', 'esc', 'ctrl+c') e letras soltas
    ('c', 'x'). Lança ValueError para nomes desconhecidos.
    """
    token = name.strip().lower()
    if token in _KEY_ALIASES:
        return _KEY_ALIASES[token]
    if len(token) == 1 and token.isalnum():
        return token
    raise ValueError(
        f"Tecla desconhecida: {name!r}. "
        "Use 'space', 'esc', 'enter', 'tab', 'backspace', 'ctrl+c' ou uma letra."
    )


def pretty_key(token: str) -> str:
    """Nome bonito para exibir ao usuário (ex.: 'space' -> 'Espaço')."""
    return _PRETTY_NAMES.get(token, token.upper() if len(token) == 1 else token)


def normalize_key(data: bytes) -> str | None:
    """Converte bytes brutos do terminal no nome canônico da tecla.

    Retorna None para bytes sem ação mapeada (ex.: bytes soltos de sequência).
    Função pura — testável sem terminal real.
    """
    if not data:
        return None

    if data in _KEY_NAMES:
        return _KEY_NAMES[data]

    # Esc puro vs início de sequência desconhecida: trata como Esc.
    if data == b"\x1b":
        return "esc"
    if data.startswith(b"\x1b"):
        return None

    if data in (b"\r", b"\n"):
        return "enter"
    if data == b"\t":
        return "tab"
    if data == b"\x7f":
        return "backspace"
    if data == b" ":
        return "space"

    ctrl = _CTRL_KEYS.get(data[0])
    if len(data) == 1 and ctrl:
        return ctrl

    try:
        char = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if char.isprintable():
        return char.lower()
    return None


class HotkeyListener:
    """Captura teclas do terminal sem bloquear o event loop asyncio.

    Uso::

        hotkeys = HotkeyListener()
        await hotkeys.start()            # no-op se stdin não for TTY
        key = await hotkeys.get_key()    # 'esc', 'enter', 'ctrl+c', 'a', ...
        hotkeys.clear()                  # descarta teclas bufferizadas
        hotkeys.stop()                   # restaura o terminal

    Atributos
    ---------
    available : bool
        True se há TTY em stdin e o listener foi iniciado. False em CI,
        pipes ou docker sem -it — o programa deve degradar sem hotkeys.
    """

    def __init__(self):
        self.available = False

        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._saved_attrs: list | termios.tcattrdata | None = None
        self._restore_registered = False

    async def start(self) -> None:
        """Ativa a captura. Seguro chamar sempre: sem TTY vira no-op."""
        if self.available:
            return
        if not sys.stdin.isatty() or not hasattr(termios, "tcgetattr"):
            logger.info("Sem TTY em stdin — hotkeys de teclado desativadas.")
            return

        loop = asyncio.get_running_loop()
        try:
            self._saved_attrs = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin)
        except Exception as exc:
            logger.warning("Falha ao colocar terminal em cbreak (%s). Hotkeys desativadas.", exc)
            self._saved_attrs = None
            return

        if not self._restore_registered:
            atexit.register(self._restore_terminal)
            self._restore_registered = True

        self._loop = loop
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True, name="hotkey-reader")
        self._thread.start()
        self.available = True
        logger.info(
            "Hotkeys ativas: tecla de cancelamento interrompe fala/pedido, Ctrl+C sai."
        )

    async def get_key(self) -> str:
        """Aguarda a próxima tecla pressionada."""
        return await self._queue.get()

    def clear(self) -> None:
        """Descarta teclas bufferizadas (evita ações fantasma entre turnos)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def stop(self) -> None:
        """Encerra a thread leitora e restaura o terminal."""
        if self._thread is not None:
            self._stop_event.set()
            self._thread.join(timeout=1.0)
            self._thread = None
        self._restore_terminal()
        self.available = False
        logger.info("Hotkeys encerradas.")

    # Interno

    def _read_loop(self) -> None:
        fd = sys.stdin.fileno()
        while not self._stop_event.is_set():
            try:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if not ready:
                    continue
                data = os.read(fd, 1)
                if not data:
                    break  # EOF
                if data == b"\x1b":
                    extra = self._drain_escape(fd)
                    if extra:
                        data += extra
                key = normalize_key(data)
                if key is not None and self._loop is not None:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, key)
            except OSError:
                break  # fd fechado durante shutdown
            except Exception as exc:
                logger.debug("Erro no leitor de teclas: %s", exc)

    @staticmethod
    def _drain_escape(fd: int) -> bytes:
        """Coleta os bytes restantes de uma sequência de escape, se houver."""
        extra = b""
        while True:
            ready, _, _ = select.select([fd], [], [], _ESCAPE_WAIT_S)
            if not ready:
                break
            try:
                chunk = os.read(fd, 8)
            except OSError:
                break
            if not chunk:
                break
            extra += chunk
            if chunk[-1:].isalpha():
                break
        return extra

    def _restore_terminal(self) -> None:
        if self._saved_attrs is None:
            return
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._saved_attrs)
        except Exception as exc:
            logger.debug("Falha ao restaurar terminal: %s", exc)
        finally:
            self._saved_attrs = None
