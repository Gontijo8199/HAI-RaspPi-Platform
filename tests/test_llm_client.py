from unittest.mock import MagicMock, patch

import pytest


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_retorna_texto(mock_genai):
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter([MagicMock(text="Resposta do tutor.")])
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    resposta = await client.send("quanto é 2 mais 2?")

    assert "Resposta do tutor." in resposta


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_strip_espacos(mock_genai):
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter([MagicMock(text="  texto com espaços  ")])
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    resposta = await client.send("teste")

    assert resposta == "texto com espaços"


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_stream_produz_tokens(mock_genai):
    chunks = [MagicMock(text=t) for t in ["Olá, ", "como ", "posso ", "ajudar?"]]
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter(chunks)
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    tokens = []
    async for token in client.send_stream("oi"):
        tokens.append(token)

    assert tokens == ["Olá, ", "como ", "posso ", "ajudar?"]


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_stream_ignora_chunks_vazios(mock_genai):
    chunks = [
        MagicMock(text="Bom dia"),
        MagicMock(text=None),
        MagicMock(text=""),
        MagicMock(text="!"),
    ]
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter(chunks)
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    tokens = []
    async for token in client.send_stream("oi"):
        tokens.append(token)

    assert tokens == ["Bom dia", "!"]


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_generate_flashcard_retorna_texto(mock_genai):
    mock_response = MagicMock()
    mock_response.text = "## Fotossíntese\n**Resumo:** conversão de luz em energia.\n- ponto 1"
    mock_genai.return_value.models.generate_content.return_value = mock_response
    mock_genai.return_value.chats.create.return_value = MagicMock()

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    flashcard = await client.generate_flashcard("explica fotossíntese")

    assert flashcard.startswith("## Fotossíntese")
    mock_genai.return_value.models.generate_content.assert_called_once()


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_generate_flashcard_strip_espacos(mock_genai):
    mock_response = MagicMock()
    mock_response.text = "  ## Título  \n"
    mock_genai.return_value.models.generate_content.return_value = mock_response
    mock_genai.return_value.chats.create.return_value = MagicMock()

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    flashcard = await client.generate_flashcard("oi")

    assert flashcard == "## Título"


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_generate_flashcard_erro_retorna_string_vazia(mock_genai):
    mock_genai.return_value.models.generate_content.side_effect = RuntimeError("boom")
    mock_genai.return_value.chats.create.return_value = MagicMock()

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    flashcard = await client.generate_flashcard("oi")

    assert flashcard == ""


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_generate_flashcard_nao_usa_chat_da_sessao(mock_genai):

    mock_response = MagicMock()
    mock_response.text = "## Título"
    mock_genai.return_value.models.generate_content.return_value = mock_response
    mock_genai.return_value.chats.create.return_value = MagicMock()

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    await client.generate_flashcard("oi")

    client._chat.send_message.assert_not_called()


@patch("google.genai.Client")
def test_resetar_sessao_cria_novo_chat(mock_genai):
    chat1 = MagicMock()
    chat2 = MagicMock()
    mock_genai.return_value.chats.create.side_effect = [chat1, chat2]

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    assert client._chat is chat1

    client.resetar_sessao()
    assert client._chat is chat2
    assert mock_genai.return_value.chats.create.call_count == 2


# ---------- Cancelamento do stream (tecla Esc) ----------


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_fechar_o_gerador_limpa_o_evento_de_cancelamento(mock_genai):
    """Consumir parcialmente o stream e fechá-lo deve sinalizar a thread de rede parar."""
    chunks = [MagicMock(text=t) for t in ["um ", "dois ", "três"]]
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter(chunks)
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    agen = client.send_stream("oi")

    primeiro = await agen.__anext__()
    assert primeiro == "um "
    assert client._cancel_event is not None  # stream em andamento

    await agen.aclose()

    assert client._cancel_event is None


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_stream_completo_limpa_o_estado_de_cancelamento(mock_genai):
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter([MagicMock(text="fim")])
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    async for _token in client.send_stream("oi"):
        pass

    assert client._cancel_event is None


@patch("google.genai.Client")
def test_cancel_stream_sem_stream_ativa_e_noop(mock_genai):
    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    client.cancel_stream()  # não lança


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_cancel_stream_sinaliza_a_thread(mock_genai):
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter([MagicMock(text="a"), MagicMock(text="b")])

    mock_chat.send_message_stream.return_value = iter([MagicMock(text="a"), MagicMock(text="b")])
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    tokens = []
    async for token in client.send_stream("oi"):
        tokens.append(token)
        if len(tokens) == 1:
            client.cancel_stream()  # sinaliza sem lançar
            break

    assert tokens == ["a"]


# ---------- Imagens (foto da webcam) ----------


def _imagem():
    from vision.image import CapturedImage

    return CapturedImage(data=b"\xff\xd8fake", width=10, height=10)


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_stream_com_imagem_envia_foto_antes_do_texto(mock_genai):
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter([MagicMock(text="É uma samambaia.")])
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    resposta = await client.send("que planta é essa?", images=[_imagem()])

    assert resposta == "É uma samambaia."
    (conteudo,) = mock_chat.send_message_stream.call_args.args
    assert isinstance(conteudo, list)
    assert conteudo[0].inline_data.data == b"\xff\xd8fake"
    assert conteudo[0].inline_data.mime_type == "image/jpeg"
    assert "que planta é essa?" in conteudo[-1]
    assert "foto" in conteudo[-1]


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_stream_sem_imagem_continua_enviando_texto_puro(mock_genai):
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter([MagicMock(text="ok")])
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    await client.send("oi")

    (conteudo,) = mock_chat.send_message_stream.call_args.args
    assert isinstance(conteudo, str)
    assert "foto" not in conteudo


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_generate_flashcard_com_imagem(mock_genai):
    mock_response = MagicMock()
    mock_response.text = "## Plantas"
    mock_genai.return_value.models.generate_content.return_value = mock_response
    mock_genai.return_value.chats.create.return_value = MagicMock()

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    flashcard = await client.generate_flashcard("que planta é essa?", images=[_imagem()])

    assert flashcard == "## Plantas"
    contents = mock_genai.return_value.models.generate_content.call_args.kwargs["contents"]
    assert isinstance(contents, list)
    assert contents[0].inline_data.data == b"\xff\xd8fake"


@patch("google.genai.Client")
def test_system_prompt_orienta_o_uso_de_imagens(mock_genai):
    from api.llm_client import LLMClient

    assert "Imagens:" in LLMClient.SYSTEM_PROMPT
    assert "pessoas" in LLMClient.SYSTEM_PROMPT


# ---------- Mensagem composta (texto e fotos intercalados) ----------


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_parts_stream_preserva_a_ordem_numa_unica_requisicao(mock_genai):
    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = iter([MagicMock(text="ok")])
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient
    from vision.image import CapturedImage

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    foto_a = CapturedImage(data=b"A", width=1, height=1)
    foto_b = CapturedImage(data=b"B", width=1, height=1)
    tokens = [t async for t in client.send_parts_stream(["compare", foto_a, "com", foto_b, "  "])]

    assert tokens == ["ok"]
    mock_chat.send_message_stream.assert_called_once()
    (conteudo,) = mock_chat.send_message_stream.call_args.args
    assert "Mensagem do aluno" in conteudo[0]
    assert conteudo[1] == "compare"
    assert conteudo[2].inline_data.data == b"A"
    assert conteudo[3] == "com"
    assert conteudo[4].inline_data.data == b"B"
    assert "2 fotos" in conteudo[5]  # texto vazio foi descartado
    assert len(conteudo) == 6


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_erro_de_rede_vira_llm_error_legivel(mock_genai):
    import httpx

    mock_chat = MagicMock()
    mock_chat.send_message_stream.side_effect = httpx.ConnectError("dns falhou")
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient, LLMError

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    with pytest.raises(LLMError, match="conexão"):
        async for _ in client.send_parts_stream(["oi"]):
            pass
    assert client._cancel_event is None


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_erro_no_meio_do_stream_entrega_tokens_e_depois_falha(mock_genai):
    def chunks():
        yield MagicMock(text="parcial")
        raise RuntimeError("caiu")

    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = chunks()
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient, LLMError

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    recebidos = []
    with pytest.raises(LLMError):
        async for token in client.send_stream("oi"):
            recebidos.append(token)
    assert recebidos == ["parcial"]


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_timeout_vira_llm_error(mock_genai):
    import threading

    liberar = threading.Event()

    def lento():
        liberar.wait(2)
        yield MagicMock(text="tarde demais")

    mock_chat = MagicMock()
    mock_chat.send_message_stream.return_value = lento()
    mock_genai.return_value.chats.create.return_value = mock_chat

    from api.llm_client import LLMClient, LLMError

    client = LLMClient(api_key="fake-key", model="gemma-fake", timeout=0.05)
    try:
        with pytest.raises(LLMError, match="demorou"):
            async for _ in client.send_stream("oi"):
                pass
    finally:
        liberar.set()


def test_describe_error_traduz_erros_da_api():
    from google.genai import errors

    from api.llm_client import describe_error

    def api_error(code, message="x"):
        return errors.APIError(code, {"error": {"code": code, "message": message}})

    assert "chave" in describe_error(api_error(401))
    assert "chave" in describe_error(api_error(400, "API key not valid"))
    assert "Limite" in describe_error(api_error(429))
    assert "problemas" in describe_error(api_error(503))
    assert describe_error(ValueError("??"))  # sempre devolve algo legível


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_resetar_sessao_durante_o_stream_nao_mistura_conversas(mock_genai):
    antigo, novo = MagicMock(), MagicMock()
    antigo.send_message_stream.return_value = iter([MagicMock(text="a"), MagicMock(text="b")])
    mock_genai.return_value.chats.create.side_effect = [antigo, novo]

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    stream = client.send_stream("oi")
    primeiro = await stream.__anext__()
    client.resetar_sessao()  # "Nova conversa" no meio da resposta
    assert [primeiro] + [t async for t in stream] == ["a", "b"]
    novo.send_message_stream.assert_not_called()
