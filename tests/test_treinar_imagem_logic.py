"""KNN do módulo Treinar reconhecedor (modules/treinar_imagem/logic.py), sem Qt."""

import numpy as np

from modules.treinar_imagem.logic import Classifier, training_problem


def unit(*values):
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_vizinha_mais_proxima_de_uma_amostra_e_ela_mesma():
    knn = Classifier()
    knn.add(0, unit(1, 0, 0))
    knn.add(1, unit(0, 1, 0))
    assert knn.predict(unit(1, 0, 0)) == {0: 1.0, 1: 0.0}  # 1 foto por classe: k = 1
    knn.add(0, unit(0.9, 0.1, 0))
    knn.add(1, unit(0.1, 0.9, 0))
    knn.add(1, unit(0, 1, 0.1))
    conf = knn.predict(unit(0, 1, 0))
    assert max(conf, key=conf.get) == 1
    assert abs(sum(conf.values()) - 1) < 1e-6


def test_sem_exemplos_nao_preve_nada():
    assert Classifier().predict(unit(1, 0)) == {}


def test_treino_exige_duas_classes_com_foto():
    assert training_problem([]) is not None
    assert training_problem([3]) is not None
    assert training_problem([2, 0]) is not None
    assert training_problem([1, 1]) is None
