"""
Quebra o stream de tokens do LLM em frases para o TTS começar a falar antes
da resposta terminar. Compartilhado pelo modo terminal (core/pipeline.py) e
pelo módulo de conversa da interface gráfica (modules/chat/session.py).

Regras:
- Fim de frase ('.', '?', '!', quebra de linha) libera a frase na hora.
- Sem fim de frase, um buffer com _MIN_TTS_CHARS ou mais é cortado na última
  vírgula (se ela não estiver no começo) ou inteiro — evita silêncio longo.
"""

SENTENCE_ENDS = {".", "?", "!", "\n"}
_MIN_TTS_CHARS = 40


class SentenceChunker:
    def __init__(self, min_chars: int = _MIN_TTS_CHARS):
        self._min_chars = min_chars
        self._buffer = ""

    def feed(self, token: str) -> list[str]:
        """Acrescenta um token e devolve as frases prontas para falar (pode ser vazio)."""
        self._buffer += token
        phrases: list[str] = []

        flush_idx = next((i for i, ch in enumerate(self._buffer) if ch in SENTENCE_ENDS), -1)
        if flush_idx >= 0:
            phrase = self._buffer[: flush_idx + 1].strip()
            self._buffer = self._buffer[flush_idx + 1 :]
            if phrase:
                phrases.append(phrase)
        elif len(self._buffer) >= self._min_chars:
            comma_idx = self._buffer.rfind(",")
            if comma_idx > self._min_chars // 2:
                phrase = self._buffer[: comma_idx + 1].strip()
                self._buffer = self._buffer[comma_idx + 1 :]
            else:
                phrase = self._buffer.strip()
                self._buffer = ""
            if phrase:
                phrases.append(phrase)
        return phrases

    def flush(self) -> str | None:
        """Devolve o que sobrou no buffer (fim do stream) e o esvazia."""
        rest = self._buffer.strip()
        self._buffer = ""
        return rest or None
