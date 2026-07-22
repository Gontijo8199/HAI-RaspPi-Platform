import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class LLMClient:
    SYSTEM_PROMPT = """\
        Você é um tutor virtual de apoio escolar para alunos do Ensino Fundamental II (6º ao 9º ano).

        Você receberá transcrições automáticas de voz geradas pelo Whisper, que podem conter
        erros de reconhecimento, palavras incompletas, repetições, hesitações ou pontuação incorreta.

        Diretrizes de interpretação:
        - Interprete a intenção da pergunta, corrigindo mentalmente apenas erros evidentes de transcrição.
        - Não invente informações nem assuma detalhes que não estejam implícitos na pergunta.
        - Diante de duas interpretações plausíveis, escolha a mais provável dado o contexto escolar.
        - Se a pergunta for incompreensível mesmo após interpretação, responda somente:
          "Não entendi sua pergunta. Pode repetir de outro jeito?"

        Diretrizes de resposta:
        - Responda sempre em português brasileiro, de forma direta e acolhedora.
        - Adapte a linguagem para adolescentes: clara, sem ser infantilizada nem técnica demais.
        - Sempre que possível, ilustre com um exemplo concreto do cotidiano.
        - Não mencione a transcrição, erros de reconhecimento nem seu funcionamento interno.
        - Limite a resposta a aproximadamente 120 palavras.

        Contexto da conversa:
        - Você está em uma sessão contínua com o mesmo aluno.
        - Use o histórico da conversa para manter coerência, retomar conceitos já explicados
          e evitar repetições desnecessárias.
        - Se o aluno fizer uma pergunta de acompanhamento, responda considerando o que já foi dito.
    """

    FLASHCARD_SYSTEM_PROMPT = """\
        Você gera flash-cards de resumo para um tutor virtual escolar.

        Dada a transcrição de uma pergunta de um aluno do Ensino Fundamental II,
        produza um flash-card curto em Markdown identificando o tópico/matéria
        sendo discutido. Formato obrigatório:

        ## <Título curto do tópico, 2 a 5 palavras>
        **Resumo:** <uma frase objetiva sobre o que está sendo discutido>
        - <ponto-chave 1, até 8 palavras>
        - <ponto-chave 2, até 8 palavras>

        Regras:
        - Responda somente com o Markdown acima, sem texto antes ou depois.
        - Português brasileiro, direto, sem jargão técnico.
        - No máximo 3 bullets.
        - Se a pergunta for incompreensível, use "## Pergunta não identificada"
          como título e um resumo genérico.
    """

    # TODO: Exportar prompts para arquivos externos

    def __init__(
        self,
        api_key: str,
        model: str = "gemma-4-26b-a4b-it",
        timeout: float = 30.0,
    ):
        self.model = model
        self.timeout = timeout
        self._client = genai.Client(api_key=api_key)
        self._chat = self._nova_sessao()

    async def send_stream(self, transcription: str) -> AsyncIterator[str]:
        mensagem = f'Transcrição do aluno:\n"""\n{transcription}\n"""'

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        cancelled = threading.Event()

        def _run_stream() -> None:
            try:
                for chunk in self._chat.send_message_stream(mensagem):
                    if cancelled.is_set():
                        break
                    text = chunk.text or ""
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
            except Exception as exc:
                logger.error("Erro no stream LLM: %s", exc)
            finally:
                if not cancelled.is_set():
                    loop.call_soon_threadsafe(queue.put_nowait, None)

        asyncio.get_running_loop().run_in_executor(None, _run_stream)

        while True:
            try:
                token = await asyncio.wait_for(queue.get(), timeout=self.timeout)
            except TimeoutError:
                logger.warning("Timeout aguardando token do LLM.")
                cancelled.set()
                break
            if token is None:
                break
            yield token

    async def send(self, transcription: str) -> str:
        tokens: list[str] = []
        async for token in self.send_stream(transcription):
            tokens.append(token)
        return "".join(tokens).strip()

    async def generate_flashcard(self, transcription: str) -> str:

        mensagem = f'Pergunta do aluno:\n"""\n{transcription}\n"""'
        loop = asyncio.get_running_loop()

        def _call() -> str:
            response = self._client.models.generate_content(
                model=self.model,
                contents=mensagem,
                config=types.GenerateContentConfig(
                    system_instruction=self.FLASHCARD_SYSTEM_PROMPT,
                ),
            )
            return (response.text or "").strip()

        try:
            return await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=self.timeout)
        except Exception as exc:
            logger.error("Erro ao gerar flashcard: %s", exc)
            return ""

    def resetar_sessao(self) -> None:
        self._chat = self._nova_sessao()
        logger.info("Sessão LLM reiniciada.")

    def _nova_sessao(self) -> Any:
        return self._client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(system_instruction=self.SYSTEM_PROMPT),
        )
