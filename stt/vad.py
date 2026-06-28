import numpy as np
import torch


class SileroVAD:
    """Wrapper do Silero VAD para classificação frame a frame.

    Exige áudio mono PCM-16 a 16 kHz em chunks de exatamente 512 amostras
    (32 ms), restrição imposta pelo modelo.

    Parâmetros
    ----------
    threshold : float
        Probabilidade mínima para classificar um frame como fala.
    sample_rate : int
        Deve ser 16000.
    """

    CHUNK_SAMPLES = 512

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        if sample_rate != 16000:
            raise ValueError("SileroVAD suporta apenas 16000 Hz.")

        self.threshold = threshold
        self.sample_rate = sample_rate

        import logging

        logging.getLogger(__name__).info("Carregando modelo Silero VAD...")
        self._model, self._utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        self._model.eval()
        logging.getLogger(__name__).info("Silero VAD pronto.")

    def reset_state(self) -> None:
        self._model.reset_states()

    def is_speech(self, pcm_chunk: bytes) -> tuple[bool, float]:
        audio = np.frombuffer(pcm_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = torch.from_numpy(audio).unsqueeze(0)

        with torch.no_grad():
            prob = self._model(tensor, self.sample_rate).item()

        return prob >= self.threshold, prob
