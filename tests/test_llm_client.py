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
    mock_chat.send_message_stream.return_value = iter(
        [MagicMock(text="a"), MagicMock(text="b")]
    )
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
