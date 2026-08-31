"""
Saída de terminal consistente para todo o pipeline: status, avisos e erros
com cores ANSI. Cores são desativadas automaticamente quando a saída não é
um TTY (CI, pipes, logs) ou quando NO_COLOR está definido.
"""

import os
import sys

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"


def _paint(color: str, text: str) -> str:
    return f"{color}{text}{_RESET}" if _TTY else text


_CANCEL_HINT = "Espaço"


def set_cancel_hint(label: str) -> None:
    """Define o rótulo da tecla de cancelamento exibido nos status."""
    global _CANCEL_HINT
    _CANCEL_HINT = label


def banner(mode: str, controls: list[tuple[str, str]]) -> None:
    """Cabeçalho inicial com modo de captura e tabela de controles."""
    print()
    print(_paint(_BOLD + _CYAN, "  HAI — Tutor Virtual"))
    print(_paint(_DIM, f"  Modo de captura: {mode}"))
    print(_paint(_DIM, "  ─────────────────────────────────────────"))
    for key, action in controls:
        print(f"  {_paint(_BOLD, key):<28}{_paint(_DIM, action)}")
    print(_paint(_DIM, "  ─────────────────────────────────────────"))
    print()


def status(msg: str) -> None:
    print(_paint(_CYAN, msg))


def listening() -> None:
    print(f"\r{_paint(_CYAN, '● Ouvindo...')}\033[K", end="", flush=True)


def recording() -> None:
    print(f"\r{_paint(_GREEN, '● GRAVANDO')}\033[K", end="", flush=True)


def transcribing() -> None:
    print(f"\r{_paint(_YELLOW, '● Transcrevendo...')}\033[K", end="", flush=True)


def thinking(utterance: str) -> None:
    print(f"\r{_paint(_MAGENTA, f'● Pensando: “{utterance}”')}\033[K")


def speaking() -> None:
    print(
        f"\r{_paint(_MAGENTA, f'● Falando... ({_CANCEL_HINT} interrompe)')}\033[K",
        end="",
        flush=True,
    )


def cancelled() -> None:
    print(f"\r{_paint(_RED, '✗ Cancelado.')}\033[K")


def cancelled_inline() -> None:
    """Versão sem quebra de linha (interrompe um stream em andamento)."""
    print(f"\r{_paint(_RED, '✗ Cancelado')}\033[K", end="", flush=True)


def discarded() -> None:
    print(f"\r{_paint(_DIM, '○ Áudio descartado (sem conteúdo detectável).')}\033[K")


def muted_mic() -> None:
    print(f"{_paint(_DIM, '  (mic mutado durante a resposta — --allow-barge-in desativa)')}")


def success(msg: str) -> None:
    print(f"{_paint(_GREEN, msg)}")


def warn(msg: str) -> None:
    print(f"{_paint(_YELLOW, msg)}")


def error(msg: str) -> None:
    print(f"{_paint(_RED, msg)}")


def dim(msg: str) -> None:
    print(f"{_paint(_DIM, msg)}")
