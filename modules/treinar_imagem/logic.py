"""
Regra da atividade: um classificador KNN sobre os vetores das fotos.

Sem Qt e sem modelo: recebe vetores já normalizados (embedder.py) e é testado
direto (tests/test_treinar_imagem_logic.py). "Treinar" um KNN é só guardar os
exemplos; a previsão vota entre as k fotos mais parecidas, como o
knn-classifier do TensorFlow.js usado na POC (k ≤ 3).
"""

from __future__ import annotations

import numpy as np

K = 3


class Classifier:
    def __init__(self):
        self._vectors: list[np.ndarray] = []
        self._labels: list[int] = []

    def add(self, label: int, vector: np.ndarray) -> None:
        self._vectors.append(vector)
        self._labels.append(label)

    def clear(self) -> None:
        self._vectors.clear()
        self._labels.clear()

    def predict(self, vector: np.ndarray) -> dict[int, float]:
        """Confiança (0–1) de cada classe que tem exemplo; somam 1."""
        if not self._vectors:
            return {}
        similarity = np.stack(self._vectors) @ vector  # cosseno: os vetores têm norma 1
        # k não passa da menor classe: com 1 foto em cada, k = 3 daria sempre empate.
        k = min(K, *(self._labels.count(label) for label in set(self._labels)))
        nearest = np.argsort(-similarity)[:k]
        confidences = dict.fromkeys(self._labels, 0.0)
        for i in nearest:
            confidences[self._labels[i]] += 1 / k
        return confidences


def training_problem(photo_counts: list[int]) -> str | None:
    """Motivo para não treinar ainda (None = pode treinar)."""
    if len(photo_counts) < 2 or 0 in photo_counts:
        return "Crie pelo menos 2 classes e ponha 1 foto em cada uma."
    return None
