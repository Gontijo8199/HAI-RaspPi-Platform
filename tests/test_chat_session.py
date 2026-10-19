"""Lógica do módulo "Conversar com a IA" (sem Qt, sem hardware, sem rede)."""

import asyncio

import pytest
from fakes import FakeASR, FakeCamera, FakeLLM, FakeRecorder, FakeTTS, Recorder, _image

from api.llm_client import LLMError
from core.services import SpeechUnavailable
from modules.chat.session import Activity, ChatSession, VoiceStatus
from vision.image import CapturedImage


async def _settle(n=10):
    for _ in range(n):
        await asyncio.sleep(0)


async def _idle(session, timeout=1.0):
    async def wait():
        while session.activity is not Activity.IDLE or session._task is not None:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout)


@pytest.fixture
def parts():
    llm, tts, recorder, asr, camera = FakeLLM(), FakeTTS(), FakeRecorder(), FakeASR(), FakeCamera()

    async def get_asr():
        return asr

    session = ChatSession(llm, tts, camera=camera, recorder=recorder, get_asr=get_asr)
    listener = Recorder()
    session.listener = listener
    return session, llm, tts, recorder, asr, camera, listener


async def _started(parts):
    session = parts[0]
    await session.start()
    await _settle()
    return parts


# ---------- ciclo de vida ----------


async def test_start_abre_o_microfone_e_prepara_a_voz(parts):
    session, llm, _tts, recorder, _asr, _cam, listener = await _started(parts)
    assert recorder.opened == 1
    assert llm.resets == 1  # cada entrada começa uma conversa nova
    assert session.voice_status is VoiceStatus.READY
    assert (
        "voice_status_changed",
        VoiceStatus.LOADING,
        "Preparando o reconhecimento de voz...",
    ) in listener.events


async def test_microfone_indisponivel_desativa_so_a_voz(parts):
    session, _llm, _tts, recorder, _asr, _cam, _l = parts
    recorder.fail_open = True
    await session.start()
    assert session.voice_status is VoiceStatus.UNAVAILABLE
    assert "microfone" in session.voice_reason
    assert session.begin_recording() is False
    session.add_text_block().text = "oi"
    assert session.send() is True  # texto continua funcionando
    await _idle(session)


async def test_whisper_indisponivel_desativa_a_voz():
    async def get_asr():
        raise SpeechUnavailable("sem modelo")

    session = ChatSession(FakeLLM(), FakeTTS(), recorder=FakeRecorder(), get_asr=get_asr)
    await session.start()
    await _settle()
    assert session.voice_status is VoiceStatus.UNAVAILABLE
    assert session.voice_reason == "sem modelo"


async def test_stop_libera_recursos_e_apaga_a_conversa(parts):
    session, llm, tts, recorder, _asr, _cam, listener = await _started(parts)
    session.add_text_block().text = "oi"
    session.send()
    await _idle(session)
    assert session.messages

    await session.stop()

    assert recorder.closed == 1
    assert session.messages == [] and session.draft == []
    assert llm.resets == 2  # entrada + saída
    assert session.listener is None


async def test_resposta_atrasada_nao_atualiza_tela_encerrada(parts):
    session, llm, _tts, _rec, _asr, _cam, listener = await _started(parts)
    llm.gate = asyncio.Event()
    session.add_text_block().text = "pergunta"
    session.send()
    await _settle()
    assert session.activity is Activity.RESPONDING

    await session.stop()
    eventos_antes = len(listener.events)
    llm.gate.set()
    await _settle(20)

    assert len(listener.events) == eventos_antes  # nada chegou depois da saída
    assert session.messages == []
    assert llm.cancels >= 1


# ---------- texto e envio ----------


async def test_mensagem_de_texto_vai_ao_llm_e_a_resposta_aparece(parts):
    session, llm, tts, _rec, _asr, _cam, listener = await _started(parts)
    block = session.add_text_block()
    session.set_text(block.id, "  quanto é 2 + 2?  ")

    assert session.send() is True
    assert session.activity is Activity.THINKING
    await _idle(session)

    assert llm.sent == [["quanto é 2 + 2?"]]
    question, reply = session.messages
    assert question.role == "user" and question.blocks[0].text.strip() == "quanto é 2 + 2?"
    assert reply.role == "ai" and reply.status == "done" and reply.text == "Olá! Tudo bem."
    assert ("message_updated", reply) in listener.events
    assert tts.spoken == ["Olá!", "Tudo bem."]  # frase a frase
    assert session.draft == []


async def test_enviar_sem_conteudo_avisa_e_nao_chama_o_llm(parts):
    session, llm, _tts, _rec, _asr, _cam, listener = await _started(parts)
    session.add_text_block()  # vazio
    assert session.send() is False
    assert llm.sent == []
    assert listener.notices("info")


async def test_envio_duplicado_e_bloqueado(parts):
    session, llm, _tts, _rec, _asr, _cam, _l = await _started(parts)
    llm.gate = asyncio.Event()
    session.add_text_block().text = "um"
    assert session.send() is True
    session.add_text_block().text = "dois"
    assert session.send() is False  # resposta em andamento
    llm.gate.set()
    await _idle(session)
    assert len(llm.sent) == 1


async def test_voz_desligada_nao_chama_o_tts(parts):
    session, _llm, tts, _rec, _asr, _cam, _l = await _started(parts)
    session.set_voice_output(False)
    session.add_text_block().text = "oi"
    session.send()
    await _idle(session)
    assert tts.spoken == []


async def test_estado_falando_enquanto_o_tts_termina(parts):
    session, _llm, tts, _rec, _asr, _cam, listener = await _started(parts)
    session.add_text_block().text = "oi"
    session.send()
    tts.busy = True  # a resposta ainda está sendo falada
    await asyncio.sleep(0.05)
    assert session.activity is Activity.SPEAKING
    tts.busy = False
    await _idle(session)
    assert ("activity_changed", Activity.SPEAKING) in listener.events


async def test_contexto_permanece_na_conversa_e_nova_conversa_limpa(parts):
    session, llm, _tts, _rec, _asr, _cam, listener = await _started(parts)
    for pergunta in ("primeira", "segunda"):
        session.add_text_block().text = pergunta
        session.send()
        await _idle(session)
    assert llm.resets == 1  # mesma sessão de chat nas duas perguntas
    assert len(session.messages) == 4

    session.add_text_block().text = "rascunho"
    session.take_photo()
    await _idle(session)
    await session.new_conversation()

    assert llm.resets == 2
    assert session.messages == [] and session.draft == []
    assert "conversation_cleared" in listener.names()
    session.take_photo()
    await _idle(session)
    assert session.draft[0].label == "foto 1"  # contador de fotos reinicia


# ---------- multimodal ----------


async def test_texto_e_fotos_vao_juntos_e_na_ordem(parts):
    session, llm, _tts, _rec, _asr, camera, _l = await _started(parts)
    session.add_text_block().text = "compare esta"
    assert session.take_photo() is True
    assert session.activity is Activity.CAPTURING
    await _idle(session)
    session.add_text_block().text = "com esta"
    session.take_photo()
    await _idle(session)

    session.send()
    await _idle(session)

    (enviado,) = llm.sent  # UMA requisição
    assert enviado[0] == "compare esta"
    assert isinstance(enviado[1], CapturedImage) and enviado[1].data == _image(1).data
    assert enviado[2] == "com esta"
    assert isinstance(enviado[3], CapturedImage) and enviado[3].data == _image(2).data
    assert [b.kind for b in session.messages[0].blocks] == ["text", "photo", "text", "photo"]


async def test_inserir_e_remover_blocos_mantem_a_ordem(parts):
    session, llm, _tts, _rec, _asr, _cam, _l = await _started(parts)
    a = session.add_text_block()
    a.text = "A"
    session.take_photo()
    await _idle(session)
    c = session.add_text_block(index=1)  # entre o texto e a foto
    session.set_text(c.id, "B")
    session.remove_block(a.id)
    session.send()
    await _idle(session)
    assert llm.sent[0][0] == "B"
    assert isinstance(llm.sent[0][1], CapturedImage)


async def test_falha_da_camera_avisa_e_nao_cria_bloco(parts):
    session, _llm, _tts, _rec, _asr, camera, listener = await _started(parts)
    camera.fail = True
    session.take_photo()
    await _idle(session)
    assert session.draft == []  # o espaço reservado para a foto sai
    (erro,) = [e for e in listener.events if e[0] == "notice" and e[1] == "error"]
    assert "câmera não respondeu" in erro[2]
    assert "ocupada" not in erro[2]  # detalhe técnico só no log
    assert erro[3] == "retry_photo"  # a tela oferece "Tentar de novo"


async def test_sem_camera_o_botao_avisa():
    session = ChatSession(FakeLLM(), FakeTTS())
    session.listener = Recorder()
    assert session.camera_available is False
    assert session.take_photo() is False


# ---------- voz ----------


async def test_gravar_transcrever_e_compor(parts):
    session, llm, _tts, recorder, asr, _cam, listener = await _started(parts)
    asr.gate = asyncio.Event()

    assert session.begin_recording() is True
    assert session.activity is Activity.RECORDING and recorder.recording
    assert session.draft[0].pending == "gravando…"
    assert session.send() is False  # não envia no meio da gravação

    session.finish_recording()
    await _settle()
    assert session.activity is Activity.TRANSCRIBING
    assert session.draft[0].pending == "transcrevendo…"
    assert session.begin_recording() is False  # sem gravações simultâneas

    asr.gate.set()
    await _idle(session)
    assert session.draft[0].pending is None
    assert session.draft[0].text == "quanto é dois mais dois"

    session.send()
    await _idle(session)
    assert llm.sent == [["quanto é dois mais dois"]]


async def test_gravacao_curta_e_descartada(parts):
    session, _llm, _tts, recorder, asr, _cam, listener = await _started(parts)
    recorder.audio = None  # VoiceRecorder.stop() devolve None quando é curta demais
    session.begin_recording()
    session.finish_recording()
    await _idle(session)
    assert session.draft == []
    assert asr.calls == 0
    assert listener.notices("info")


async def test_cancelar_gravacao_descarta_o_audio(parts):
    session, _llm, _tts, recorder, asr, _cam, _l = await _started(parts)
    session.begin_recording()
    session.cancel()
    await _idle(session)
    assert recorder.discarded == 1
    assert session.draft == [] and asr.calls == 0


async def test_cancelar_transcricao_remove_o_bloco(parts):
    session, _llm, _tts, _rec, asr, _cam, _l = await _started(parts)
    asr.gate = asyncio.Event()
    session.begin_recording()
    session.finish_recording()
    await _settle()
    session.cancel()
    await _idle(session)
    asr.gate.set()
    await _settle()
    assert session.draft == []


async def test_gravar_durante_a_fala_interrompe_o_tts(parts):
    session, _llm, tts, _rec, _asr, _cam, _l = await _started(parts)
    session.add_text_block().text = "oi"
    session.send()
    tts.busy = True  # a resposta ainda está sendo falada
    await asyncio.sleep(0.05)
    assert session.activity is Activity.SPEAKING

    assert session.begin_recording() is True
    assert tts.stops >= 1
    await asyncio.sleep(0.15)  # a tarefa antiga não pode sobrescrever o estado
    assert session.activity is Activity.RECORDING


# ---------- falhas e cancelamento ----------


async def test_falha_de_rede_nao_quebra_e_devolve_o_rascunho(parts):
    session, llm, _tts, _rec, _asr, _cam, listener = await _started(parts)
    llm.tokens = []
    llm.error = LLMError("Sem conexão com o serviço de IA.")
    session.add_text_block().text = "pergunta"
    session.send()
    await _idle(session)

    reply = session.messages[-1]
    assert reply.status == "error" and "Sem conexão" in reply.error
    assert [b.text for b in session.draft] == ["pergunta"]  # pronto para tentar de novo
    assert listener.notices("error")

    llm.error = None
    llm.tokens = ["Agora foi."]
    assert session.send() is True
    await _idle(session)
    assert session.messages[-1].status == "done"


async def test_erro_inesperado_tambem_e_tratado(parts):
    session, llm, _tts, _rec, _asr, _cam, _l = await _started(parts)
    llm.tokens = []
    llm.error = RuntimeError("boom")
    session.add_text_block().text = "x"
    session.send()
    await _idle(session)
    assert session.messages[-1].status == "error"
    assert session.messages[-1].error  # mensagem legível, sem traceback


async def test_resposta_vazia_vira_erro(parts):
    session, llm, _tts, _rec, _asr, _cam, _l = await _started(parts)
    llm.tokens = []
    session.add_text_block().text = "x"
    session.send()
    await _idle(session)
    assert session.messages[-1].status == "error"
    assert session.draft


async def test_cancelar_resposta_interrompe_e_devolve_o_rascunho(parts):
    session, llm, tts, _rec, _asr, _cam, listener = await _started(parts)
    llm.gate = asyncio.Event()
    session.add_text_block().text = "pergunta longa"
    session.send()
    await _settle()

    session.cancel()
    await _idle(session)

    assert session.messages[-1].status == "cancelled"
    assert [b.text for b in session.draft] == ["pergunta longa"]
    assert llm.cancels >= 1 and tts.stops >= 1
    llm.gate.set()
    await _settle()
    assert session.messages[-1].status == "cancelled"  # token atrasado não reabre a resposta


async def test_nova_conversa_durante_resposta_descarta_o_resultado(parts):
    session, llm, _tts, _rec, _asr, _cam, _l = await _started(parts)
    llm.gate = asyncio.Event()
    session.add_text_block().text = "pergunta"
    session.send()
    await _settle()
    await session.new_conversation()
    llm.gate.set()
    await _settle(20)
    assert session.messages == [] and session.draft == []
    assert session.activity is Activity.IDLE
    assert session.voice_status is VoiceStatus.READY  # a voz continua pronta


async def test_erro_na_tela_nao_derruba_a_sessao(parts):
    session, _llm, _tts, _rec, _asr, _cam, _l = await _started(parts)

    class Quebrada:
        def __getattr__(self, name):
            def boom(*_a):
                raise RuntimeError("widget morto")

            return boom

    session.listener = Quebrada()
    session.add_text_block().text = "oi"
    session.send()
    await _idle(session)
    assert session.messages[-1].status == "done"


# ---------- rascunho editado na tela (editor único) ----------


async def test_replace_draft_segue_a_ordem_da_tela_e_mantem_as_fotos(parts):
    session, llm, *_rest = await _started(parts)
    session.take_photo()
    await _idle(session)
    (foto,) = session.draft

    session.replace_draft(["antes ", foto.id, " depois", 999, ""])  # 999: apagada; "": ignorado
    assert [b.kind for b in session.draft] == ["text", "photo", "text"]
    assert session.draft[1] is foto

    session.send()
    await _idle(session)
    (enviado,) = llm.sent
    assert enviado[0] == "antes" and enviado[2] == "depois"
    assert enviado[1] is foto.image


async def test_foto_e_voz_entram_na_posicao_pedida(parts):
    session, llm, *_rest = await _started(parts)
    session.replace_draft(["inicio", "fim"])

    session.take_photo(index=1)
    assert session.draft[1].pending == "tirando foto…"  # posição reservada já na tela
    assert session.send() is False  # nada sai com captura em andamento
    await _idle(session)
    assert [b.kind for b in session.draft] == ["text", "photo", "text"]
    assert session.draft[1].pending is None and session.draft[1].label == "foto 1"

    assert session.begin_recording(index=1)
    session.finish_recording()
    await _idle(session)
    assert [b.kind for b in session.draft] == ["text", "text", "photo", "text"]
    assert session.draft[1].text == "quanto é dois mais dois"


async def test_foto_nova_avisa_a_tela_e_foca_o_bloco(parts):
    session, *_rest, listener = await _started(parts)
    session.take_photo()
    await _idle(session)
    (foto,) = session.draft
    assert ("photo_captured", foto) in listener.events
    assert ("draft_changed", session.draft, foto.id) in listener.events


async def test_limite_de_fotos_por_pergunta(parts):
    from modules.chat.session import MAX_PHOTOS

    session, *_rest, listener = await _started(parts)
    for _ in range(MAX_PHOTOS):
        assert session.take_photo()
        await _idle(session)
    assert session.take_photo() is False
    assert any("até" in n for n in listener.notices("info"))


async def test_cancelar_a_captura_remove_o_espaco_da_foto(parts):
    session, _llm, _tts, _rec, _asr, camera, _l = await _started(parts)
    camera.gate = asyncio.Event()
    session.take_photo()
    await _settle()
    assert session.activity is Activity.CAPTURING
    session.cancel()
    await _idle(session)
    assert session.draft == []


async def test_editar_durante_a_resposta_e_restaurado_junto_em_caso_de_erro(parts):
    session, llm, *_rest = await _started(parts)
    llm.gate = asyncio.Event()
    llm.error = LLMError("Sem conexão com o serviço de IA.")
    session.replace_draft(["primeira pergunta"])
    session.send()
    await _settle()
    session.replace_draft(["próxima pergunta"])  # o aluno escreve enquanto espera
    llm.gate.set()
    await _idle(session)
    assert [b.text for b in session.draft] == ["primeira pergunta", "próxima pergunta"]


# ---------- microfone sem sinal / nada reconhecido ----------


async def test_transcricao_vazia_avisa_e_nao_escreve_no_editor(parts):
    session, llm, _tts, _rec, asr, _cam, listener = await _started(parts)
    asr.text = "   "
    session.replace_draft(["minha pergunta"])
    session.begin_recording()
    session.finish_recording()
    await _idle(session)
    assert [b.text for b in session.draft] == ["minha pergunta"]  # nada foi acrescentado
    assert any("Não ouvi nada" in n for n in listener.notices("error"))


async def test_microfone_mudo_nao_chama_o_whisper(parts):
    session, _llm, _tts, recorder, asr, _cam, listener = await _started(parts)
    recorder.audio = b"\x00\x00" * 16000  # 1 s de silêncio digital
    session.begin_recording()
    session.finish_recording()
    await _idle(session)
    assert asr.calls == 0
    assert session.draft == []
    assert any("microfone não captou som" in n for n in listener.notices("error"))


def test_nivel_de_audio():
    from fakes import SPEECH_PCM

    from modules.chat.session import SILENCE_RMS, audio_level

    assert audio_level(b"") == 0.0
    assert audio_level(b"\x00\x00" * 100) == 0.0
    assert audio_level(SPEECH_PCM) > 100 * SILENCE_RMS
