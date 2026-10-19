"""
Lista de dicionários exposta à QML como modelo (ListView, Repeater).

Cada chave do dicionário vira um papel (role) com o mesmo nome. update()
avisa só os papéis que mudaram, então a QML redesenha só aquele item (o
streaming de uma resposta não refaz o histórico inteiro).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    Signal,
    Slot,
)


class ListModel(QAbstractListModel):
    countChanged = Signal()

    def __init__(self, roles: list[str], parent: QObject | None = None):
        super().__init__(parent)
        self._names = list(roles)
        first = int(Qt.ItemDataRole.UserRole) + 1
        self._role_of = {name: first + i for i, name in enumerate(roles)}
        self._name_of = {role: name for name, role in self._role_of.items()}
        self._rows: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ Qt

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._name_of.get(role)
        return self._rows[index.row()].get(name) if name else None

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name.encode()) for name, role in self._role_of.items()}

    def _count(self) -> int:
        return len(self._rows)

    count = Property(int, _count, notify=countChanged)

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict[str, Any]:
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}

    # ------------------------------------------------------------------ Python

    @property
    def rows(self) -> list[dict[str, Any]]:
        return self._rows

    def append(self, row: dict[str, Any]) -> None:
        position = len(self._rows)
        self.beginInsertRows(QModelIndex(), position, position)
        self._rows.append({name: row.get(name) for name in self._names})
        self.endInsertRows()
        self.countChanged.emit()

    def update(self, row: int, **changes: Any) -> None:
        current = self._rows[row]
        changed = [name for name, value in changes.items() if current.get(name) != value]
        if not changed:
            return
        current.update({name: changes[name] for name in changed})
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self._role_of[name] for name in changed])

    def find(self, key: str, value: Any) -> int:
        return next((i for i, row in enumerate(self._rows) if row.get(key) == value), -1)

    def clear(self) -> None:
        if not self._rows:
            return
        self.beginResetModel()
        self._rows = []
        self.endResetModel()
        self.countChanged.emit()
