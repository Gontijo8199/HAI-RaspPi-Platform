"""
Fluxo por utterance:
1. STT entrega texto via queue.
2. Pipeline dispara asyncio.Task para chamar LLM com streaming.
3. Um único stream de tokens é consumido e enviado simultaneamente ao
   display (terminal) e ao TTS — sem chamar a API duas vezes.
4. TTS sintetiza e reproduz em thread daemon, sem bloquear novas utterances.
5. Próximo utterance pode iniciar enquanto o TTS ainda fala o anterior.
"""

import asyncio
import logging
import re

from api.llm_client import LLMClient
from tts.speaker import TTSSpeaker

logger = logging.getLogger(__name__)

RESET_TRIGGERS = {"resetar", "reset", "nova sessão", "novo assunto", "recomeçar"}
_VALID_TEXT = re.compile(r"[a-zA-Z0-9á-úÁ-Ú]")


class HAIPipeline:
    """Orquestra STT -> LLM -> TTS de forma assíncrona e não-bloqueante.

    Parâmetros
    ----------
    llm_client : LLMClient
        Cliente LLM já configurado.
    tts : TTSSpeaker
        Speaker TTS já inicializado.
    display_fn : callable | None
        Função chamada com a resposta completa para atualizar o display.
        Deve ter assinatura (text: str) -> None.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tts: TTSSpeaker,
        display_fn=None,
    ):
        self._llm = llm_client
        self._tts = tts
        self._display_fn = display_fn
        self._active_tasks: set[asyncio.Task] = set()

    def process_utterance(self, utterance: str) -> None:
        if not _VALID_TEXT.search(utterance):
            logger.debug("Utterance ignorada (sem conteúdo válido): %r", utterance)
            return

        task = asyncio.create_task(
            self._handle_utterance(utterance), name=f"pipeline-{id(utterance)}"
        )
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    async def _handle_utterance(self, utterance: str) -> None:
        # Verifica trigger de reset
        if utterance.strip().lower() in RESET_TRIGGERS:
            self._llm.resetar_sessao()
            self._tts.stop_speaking()
            print("\n[SESSÃO REINICIADA] Histórico apagado.")
            return

        print(f'\n[ENVIANDO PARA LLM] -> "{utterance}"')

        response_parts: list[str] = []
        tts_buffer = ""
        SENTENCE_ENDS = {".", "?", "!", "\n"}
        MIN_CHARS = 40

        try:
            async for token in self._llm.send_stream(utterance):
                response_parts.append(token)
                print(token, end="", flush=True)

                tts_buffer += token
                flush_idx = next((i for i, ch in enumerate(tts_buffer) if ch in SENTENCE_ENDS), -1)

                if flush_idx >= 0:
                    phrase = tts_buffer[: flush_idx + 1].strip()
                    tts_buffer = tts_buffer[flush_idx + 1 :]
                    if phrase:
                        self._tts.speak(phrase)
                elif len(tts_buffer) >= MIN_CHARS:
                    comma_idx = tts_buffer.rfind(",")
                    if comma_idx > MIN_CHARS // 2:
                        phrase = tts_buffer[: comma_idx + 1].strip()
                        tts_buffer = tts_buffer[comma_idx + 1 :]
                    else:
                        phrase = tts_buffer.strip()
                        tts_buffer = ""
                    if phrase:
                        self._tts.speak(phrase)

            # Flush do buffer restante
            if tts_buffer.strip():
                self._tts.speak(tts_buffer.strip())

        except Exception as exc:
            logger.error("Erro no pipeline LLM→TTS: %s", exc)
            print(f"\n[ERRO NA API] {exc}")
            return

        full_response = "".join(response_parts).strip()
        print()

        if self._display_fn and full_response:
            try:
                self._display_fn(full_response)
            except Exception as exc:
                logger.warning("Erro no display: %s", exc)

    async def wait_pending(self) -> None:
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
