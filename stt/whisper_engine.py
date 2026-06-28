"""
- vad_filter=True -> remove silêncio interno antes de passar ao modelo, reduzindo o áudio real que o decoder precisa processar.
- beam_size=1 -> greedy decoding; corta latência em ~30-40 % na CPU sem perda perceptível para transcrições curtas.
- word_timestamps=False (explícito) -> desliga alinhamento por palavra, economizando memória e tempo pós-processamento.
- condition_on_previous_text=False -> evita que o decoder gaste ciclos condicionando ao histórico; cada utterance é independente.
"""

import asyncio
import logging

import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class WhisperEngine:
    """Wrapper assíncrono do faster_whisper.WhisperModel.

    O modelo é carregado uma única vez e mantido em memória.
    A transcrição roda em asyncio.to_thread para nunca bloquear o event loop.

    Parâmetros
    ----------
    model_size : str
        Tamanho do modelo. 'small' é o ponto ideal velocidade/qualidade
        para pt-BR em CPU; 'tiny' se a latência ainda for alta demais.
    device : str
        'cpu' para Raspberry Pi.
    compute_type : str
        'int8' — quantização de 8 bits, ~2–4× mais rápido que float32 na CPU.
    language : str
        Código BCP-47 do idioma (ex.: 'pt').
    beam_size : int
        1 = greedy (mais rápido), ≥2 = beam search (mais preciso, mais lento).
    initial_prompt : str | None
        Contexto de domínio; reduz erros de vocabulário técnico/escolar.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "pt",
        beam_size: int = 1,
        initial_prompt: str | None = (
            "Olá. Sou um tutor de ensino fundamental virtual. Como posso te ajudar hoje?"
        ),
    ):
        self.language = language
        self.beam_size = beam_size
        self.initial_prompt = initial_prompt

        logger.info("Carregando Whisper '%s' (%s, %s)...", model_size, device, compute_type)
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("Whisper pronto.")

    async def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        """Transcreve PCM-16 mono de forma não-bloqueante."""
        return await asyncio.to_thread(self._transcribe_sync, pcm_bytes, sample_rate)

    def _transcribe_sync(self, pcm_bytes: bytes, sample_rate: int) -> str:
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            temperature=0.0,
            # VAD interno do faster-whisper remove silêncio antes do decoder.
            # Complementa (não substitui) o SileroVAD upstream
            # age sobre trechos de silêncio que escaparam do VAD de onset/offset.
            vad_filter=True,
            vad_parameters={
                "threshold": 0.45,  # levemente mais sensível que o padrão
                "min_silence_duration_ms": 300,
                "speech_pad_ms": 200,  # padding mínimo para não cortar sílabas
            },
            condition_on_previous_text=False,
            word_timestamps=False,
            initial_prompt=self.initial_prompt,
            log_prob_threshold=-0.85,
            no_speech_threshold=0.6,
        )

        return " ".join(s.text for s in segments).strip()
