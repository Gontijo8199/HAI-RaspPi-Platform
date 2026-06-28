from unittest.mock import MagicMock, patch

import pytest


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_retorna_texto(mock_genai):
    # Simula stream com um único chunk
    mock_chunk = MagicMock()
    mock_chunk.text = "Resposta do tutor."
    mock_genai.return_value.models.generate_content_stream.return_value = iter([mock_chunk])
    mock_genai.return_value.chats.create.return_value = MagicMock()

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    resposta = await client.send("quanto é 2 mais 2?")

    assert "Resposta do tutor." in resposta


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_strip_espacos(mock_genai):
    mock_chunk = MagicMock()
    mock_chunk.text = "  texto com espaços  "
    mock_genai.return_value.models.generate_content_stream.return_value = iter([mock_chunk])
    mock_genai.return_value.chats.create.return_value = MagicMock()

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    resposta = await client.send("teste")

    assert resposta == "texto com espaços"


@patch("google.genai.Client")
@pytest.mark.asyncio
async def test_send_stream_produz_tokens(mock_genai):
    chunks = [MagicMock(text=t) for t in ["Olá, ", "como ", "posso ", "ajudar?"]]
    mock_genai.return_value.models.generate_content_stream.return_value = iter(chunks)
    mock_genai.return_value.chats.create.return_value = MagicMock()

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
    mock_genai.return_value.models.generate_content_stream.return_value = iter(chunks)
    mock_genai.return_value.chats.create.return_value = MagicMock()

    from api.llm_client import LLMClient

    client = LLMClient(api_key="fake-key", model="gemma-fake")
    tokens = []
    async for token in client.send_stream("oi"):
        tokens.append(token)

    assert tokens == ["Bom dia", "!"]


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
