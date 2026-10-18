from tts.chunker import SentenceChunker


def test_fim_de_frase_libera_na_hora():
    chunker = SentenceChunker()
    assert chunker.feed("Olá") == []
    assert chunker.feed(", tudo bem? Eu") == ["Olá, tudo bem?"]
    assert chunker.flush() == "Eu"
    assert chunker.flush() is None


def test_buffer_longo_sem_ponto_corta_na_virgula():
    chunker = SentenceChunker(min_chars=40)
    frases = chunker.feed("uma frase bem comprida que segue sem parar, e continua mais")
    assert frases == ["uma frase bem comprida que segue sem parar,"]
    assert chunker.flush() == "e continua mais"


def test_buffer_longo_sem_virgula_sai_inteiro():
    chunker = SentenceChunker(min_chars=10)
    assert chunker.feed("abcdefghijklmno") == ["abcdefghijklmno"]
