"""
Estado e ações da tela do módulo de exemplo (Page.qml só lê e chama isto).

Sem regra da atividade aqui: analyze() vem de logic.py. O controller só
transforma o resultado (ou o motivo da recusa) no que a tela mostra.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Property, QObject, Signal, Slot

from modules.exemplo.logic import InvalidInput, analyze, describe


class ExampleController(QObject):
    changed = Signal()

    def __init__(self, title: str, go_back: Callable[[], None]):
        super().__init__()
        self._title = title
        self._go_back = go_back
        self._verdict = ""
        self._details = ""
        self._error = False
        self._closed = False

    # ------------------------------------------------------------------ estado

    def _get_title(self) -> str:
        return self._title

    def _get_verdict(self) -> str:
        return self._verdict

    def _get_details(self) -> str:
        return self._details

    def _get_error(self) -> bool:
        return self._error

    title = Property(str, _get_title, constant=True)
    verdict = Property(str, _get_verdict, notify=changed)
    details = Property(str, _get_details, notify=changed)
    error = Property(bool, _get_error, notify=changed)

    # ------------------------------------------------------------------ ações

    @Slot(str, result=bool)
    def check(self, text: str) -> bool:
        """Valida a entrada e mostra o resultado ou o motivo da recusa.
        Retorna False se a entrada foi recusada (a tela seleciona o campo)."""
        if self._closed:
            return False
        try:
            result = analyze(text)
        except InvalidInput as exc:
            self._show("Entrada inválida", str(exc), error=True)
            return False
        self._show(*describe(result), error=False)
        return True

    @Slot()
    def clear(self) -> None:
        self._show("", "", error=False)

    @Slot()
    def back(self) -> None:
        if not self._closed:
            self._go_back()

    def close(self) -> None:
        self._closed = True

    def _show(self, verdict: str, details: str, *, error: bool) -> None:
        self._verdict, self._details, self._error = verdict, details, error
        self.changed.emit()
