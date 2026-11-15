"""Controller do módulo Treinar reconhecedor com câmera e extrator de mentira."""

import asyncio

from fakes import FakeCamera, FakeEmbedder
from qthelpers import until

from modules.treinar_imagem.controller import TrainerController
from modules.treinar_imagem.embedder import EmbedderError
from ui import images


def make(camera=None, embedder=None):
    tasks = []
    embedder = embedder or FakeEmbedder()

    async def get_embedder():
        if isinstance(embedder, Exception):
            raise embedder
        return embedder

    def spawn(coro):
        tasks.append(asyncio.get_running_loop().create_task(coro))

    controller = TrainerController(
        "Treinar", lambda: None, camera or FakeCamera(), get_embedder, spawn
    )
    return controller, tasks


async def run(tasks):
    await asyncio.gather(*tasks)
    tasks.clear()


async def test_treina_e_testa():
    camera = FakeCamera()
    c, tasks = make(camera)
    assert c.classes.rowCount() == 2

    c.train()
    assert c.error and "2 classes" in c.status  # sem fotos ainda

    c.addPhoto(0)  # foto 1
    await run(tasks)
    c.addPhoto(1)  # foto 2
    await run(tasks)
    assert [r["photos"] for r in c.classes.rows] == [1, 1]
    assert c.photo.startswith("image://")

    c.test()
    assert c.error and "Treine" in c.status

    c.train()
    assert c.trained and not c.error
    camera.count = 1  # próxima foto igual à 2 (classe 1)
    c.test()
    await run(tasks)
    rows = c.classes.rows
    assert rows[1]["winner"] and not rows[0]["winner"]
    assert "Classe 2" in c.status
    c.close()
    assert images.stored() == 0


async def test_toque_duplo_tira_uma_foto_so():
    camera = FakeCamera()
    c, tasks = make(camera)
    c.addPhoto(0)
    c.addPhoto(0)  # antes de a primeira tarefa começar
    assert c.busy and len(tasks) == 1
    await run(tasks)
    assert camera.count == 1 and not c.busy
    c.close()


async def test_previa_ao_vivo_e_usada_nas_fotos_e_fecha_na_saida():
    camera = FakeCamera()
    c, tasks = make(camera)
    c.start()
    await until(lambda: c.live)
    first = c.photo
    await until(lambda: c.photo != first)  # a prévia troca de quadro
    assert images.stored() == 1  # só o quadro mostrado fica na memória
    c.addPhoto(0)
    await until(lambda: c.classes.rows[0]["photos"] == 1)
    assert camera.count == 0  # foto veio da prévia, sem abrir a câmera de novo
    c.close()
    await asyncio.gather(*tasks)
    assert camera.lives[0].closed == 1 and images.stored() == 0


async def test_sem_previa_cai_na_foto_por_toque():
    camera = FakeCamera(live_fail=True)
    c, tasks = make(camera)
    c.start()
    await run(tasks)
    assert c.error and "Sem prévia" in c.status and not c.live
    assert camera.lives[0].closed == 1
    c.addPhoto(0)
    await run(tasks)
    assert camera.count == 1 and c.classes.rows[0]["photos"] == 1
    c.close()


async def test_erro_do_extrator_vira_aviso():
    c, tasks = make(embedder=EmbedderError("O modelo de imagem não foi baixado."))
    c.addPhoto(0)
    await run(tasks)
    assert c.error and "não foi baixado" in c.status
    assert not c.busy
    assert c.classes.rows[0]["photos"] == 0
    c.close()


async def test_erro_da_camera_vira_aviso():
    c, tasks = make(FakeCamera(fail=True))
    c.addPhoto(0)
    await run(tasks)
    assert c.error and "câmera" in c.status
    c.close()


async def test_renomear_e_nova_classe():
    c, _ = make()
    c.rename(0, "  Gato ")
    c.rename(1, "   ")  # vazio: mantém
    c.newClass()
    assert [r["name"] for r in c.classes.rows] == ["Gato", "Classe 2", "Classe 3"]
    c.close()


async def test_depois_de_fechar_ignora_tudo():
    camera = FakeCamera()
    camera.gate = asyncio.Event()
    c, tasks = make(camera)
    c.addPhoto(0)
    await asyncio.sleep(0)
    c.close()
    camera.gate.set()
    await run(tasks)
    assert c.classes.rows[0]["photos"] == 0
    c.newClass()
    c.addPhoto(0)
    assert c.classes.rowCount() == 2 and tasks == []
    assert images.stored() == 0
