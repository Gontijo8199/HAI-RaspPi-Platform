"""Controller do módulo Gerar imagem com um LLM de mentira."""

import asyncio

from fakes import FakeLLM

from api.llm_client import LLMError
from modules.gerar_imagem.controller import ImageGenController
from ui import images


def make(llm):
    tasks = []

    def spawn(coro):
        tasks.append(asyncio.get_running_loop().create_task(coro))

    return ImageGenController("Gerar", lambda: None, llm, spawn), tasks


async def test_gera_e_mostra_a_imagem():
    llm = FakeLLM()
    c, tasks = make(llm)
    c.generate("  um gato na lua ")
    assert c.busy
    await asyncio.gather(*tasks)
    assert llm.image_prompts == ["um gato na lua"]
    assert c.image.startswith("image://") and not c.error and not c.busy
    first = c.image
    c.generate("outro")
    await asyncio.gather(*tasks)
    assert c.image != first  # endereço novo: o Qt não reaproveita o cache
    assert images.stored() == 1  # só a última fica na memória
    c.close()
    assert images.stored() == 0


async def test_descricao_vazia_e_recusada():
    llm = FakeLLM()
    c, tasks = make(llm)
    c.generate("   ")
    assert c.error and tasks == [] and llm.image_prompts == []
    c.close()


async def test_erro_da_api_vira_aviso():
    c, tasks = make(FakeLLM(error=LLMError("Limite de uso da IA atingido.")))
    c.generate("gato")
    await asyncio.gather(*tasks)
    assert c.error and "Limite" in c.status and not c.busy and c.image == ""
    c.close()


async def test_resultado_depois_de_fechar_e_ignorado():
    llm = FakeLLM()
    llm.gate = asyncio.Event()
    c, tasks = make(llm)
    c.generate("gato")
    await asyncio.sleep(0)
    c.close()
    llm.gate.set()
    await asyncio.gather(*tasks)
    assert c.image == "" and images.stored() == 0
