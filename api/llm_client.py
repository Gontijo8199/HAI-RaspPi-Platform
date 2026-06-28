import asyncio
import logging
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

        # Fila de comunicação entre a thread de I/O e o event loop
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _run_stream() -> None:
            try:
                # A SDK sincrona itera sobre chunks; cada um vai para a fila
                for chunk in self._client.models.generate_content_stream(
                    model=self.model,
                    contents=mensagem,
                    config=types.GenerateContentConfig(
                        system_instruction=self.SYSTEM_PROMPT,
                    ),
                ):
                    text = chunk.text or ""
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
            except Exception as exc:
                logger.error("Erro no stream LLM: %s", exc)
            finally:
                # Sinaliza fim do stream com sentinela None
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # Inicia a thread sem bloquear o event loop
        asyncio.get_running_loop().run_in_executor(None, _run_stream)

        # Consome a fila de forma assíncrona
        while True:
            try:
                token = await asyncio.wait_for(queue.get(), timeout=self.timeout)
            except TimeoutError:
                logger.warning("Timeout aguardando token do LLM.")
                break
            if token is None:
                break
            yield token

    async def send(self, transcription: str) -> str:
        tokens: list[str] = []
        async for token in self.send_stream(transcription):
            tokens.append(token)
        return "".join(tokens).strip()

    def resetar_sessao(self) -> None:
        self._chat = self._nova_sessao()
        logger.info("Sessão LLM reiniciada.")

    def _nova_sessao(self) -> Any:
        return self._client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(system_instruction=self.SYSTEM_PROMPT),
        )
