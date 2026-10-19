"""
Configuração e serviços compartilhados (LLM, TTS, câmera, Whisper).

Os serviços são criados UMA vez por execução e reaproveitados por todos os
módulos — voltar ao menu não recarrega o Whisper nem recria o cliente LLM.
O que é específico de uma atividade (microfone aberto, histórico, fotos)
pertence ao módulo e é liberado na saída dele.

Nenhum serviço abre dispositivo na construção: a câmera abre a cada foto, o
microfone só existe dentro do módulo (make_recorder) e o Whisper carrega na
primeira chamada de get_asr(). Um módulo que não usa esses serviços (ex.:
modules/exemplo) não paga por eles.

Falhas de configuração não derrubam a aplicação: viram mensagens legíveis
(`config_problems`, `llm_problem`) que o menu mostra ao usuário.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tts.speaker import TTSSpeaker
from vision.camera import CameraCapture

if TYPE_CHECKING:
    from api.llm_client import LLMClient
    from stt.recorder import VoiceRecorder
    from stt.whisper_engine import WhisperEngine

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.toml"
SECRETS_PATH = CONFIG_DIR / "secrets.toml"

DEFAULT_MODEL = "gemma-4-26b-a4b-it"


class SpeechUnavailable(RuntimeError):
    """O reconhecimento de voz (Whisper) não pôde ser carregado."""


def _read_toml(path: Path, label: str, problems: list[str]) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        problems.append(f"Arquivo {label} não encontrado.")
    except tomllib.TOMLDecodeError as exc:
        problems.append(f"Arquivo {label} com erro de formatação: {exc}")
    except OSError as exc:
        problems.append(f"Não consegui ler {label}: {exc}")
    return {}


def load_config(
    settings_path: Path = SETTINGS_PATH, secrets_path: Path = SECRETS_PATH
) -> tuple[dict, dict, list[str]]:
    """Lê settings.toml e secrets.toml. Retorna (settings, secrets, problemas).

    Arquivo ausente ou inválido vira um problema descrito (e um dict vazio),
    nunca uma exceção: a interface mostra o aviso em vez de fechar.
    """
    problems: list[str] = []
    settings = _read_toml(settings_path, "config/settings.toml", problems)
    if problems:
        problems[-1] += " Usando os padrões (copie config/settings.example.toml)."
    secrets = _read_toml(secrets_path, "config/secrets.toml", problems)
    return settings, secrets, problems


class NullTTS:
    """TTS desligado (--no-tts): mesma interface do TTSSpeaker, sem áudio."""

    def speak(self, text: str) -> None:
        pass

    def stop_speaking(self) -> None:
        pass

    def is_busy(self) -> bool:
        return False

    def shutdown(self) -> None:
        pass


def build_tts(settings: dict, tts_backend: str | None, no_tts: bool) -> TTSSpeaker | NullTTS:
    if no_tts:
        logger.info("TTS desativado por --no-tts.")
        return NullTTS()
    tts_cfg = settings.get("tts", {})
    backend = tts_backend or tts_cfg.get("backend", "piper")
    return TTSSpeaker(
        backend=backend,
        # PIPER_BIN/PIPER_MODEL: definidos no Dockerfile; o settings.toml tem prioridade.
        piper_bin=tts_cfg.get("piper_bin") or os.environ.get("PIPER_BIN", "piper"),
        piper_model=tts_cfg.get("piper_model") or os.environ.get("PIPER_MODEL", ""),
        rate=tts_cfg.get("rate", 160),
        lang=tts_cfg.get("lang", "pt-br"),
    )


def build_camera(settings: dict) -> CameraCapture | None:
    cam_cfg = settings.get("camera", {})
    if not cam_cfg.get("enabled", True):
        logger.info("Câmera desativada via config/settings.toml [camera] enabled=false.")
        return None
    return CameraCapture(
        device=cam_cfg.get("device", 0),
        width=cam_cfg.get("width", 1280),
        height=cam_cfg.get("height", 720),
        max_side=cam_cfg.get("max_side", 1024),
        jpeg_quality=cam_cfg.get("jpeg_quality", 85),
        warmup_frames=cam_cfg.get("warmup_frames", 8),
        save_dir=cam_cfg.get("save_dir") or None,
    )


def build_llm(settings: dict, secrets: dict) -> tuple[LLMClient | None, str | None]:
    """Cria o cliente LLM. Retorna (cliente, None) ou (None, motivo legível)."""
    api_key = secrets.get("api", {}).get("key", "")
    if not api_key:
        return None, "Chave da API não configurada: defina [api] key em config/secrets.toml."
    api_cfg = settings.get("api", {})
    model = api_cfg.get("model") or DEFAULT_MODEL
    try:
        from api.llm_client import LLMClient

        timeout = float(api_cfg.get("timeout_s", 30.0))
        return LLMClient(api_key=api_key, model=model, timeout=timeout), None
    except Exception as exc:
        logger.error("Falha ao criar o cliente LLM: %s", type(exc).__name__)
        return None, f"Não consegui iniciar o cliente da IA ({type(exc).__name__})."


class Services:
    """Serviços compartilhados de uma execução da aplicação.

    Parâmetros
    ----------
    settings, secrets : dict
        Conteúdo de config/settings.toml e config/secrets.toml.
    tts_backend : str | None
        Força um backend de TTS (senão usa [tts] backend).
    no_tts : bool
        Desliga a síntese de voz.
    config_problems : list[str]
        Problemas encontrados por load_config(), exibidos no menu.
    """

    def __init__(
        self,
        settings: dict,
        secrets: dict,
        *,
        tts_backend: str | None = None,
        no_tts: bool = False,
        config_problems: list[str] | None = None,
    ):
        self.settings = settings
        self.config_problems = list(config_problems or [])
        self.llm, self.llm_problem = build_llm(settings, secrets)
        self.tts: Any = build_tts(settings, tts_backend, no_tts)
        self.camera = build_camera(settings)
        # Preferência de interface lida pelos módulos que têm campos de texto.
        self.on_screen_keyboard = bool(settings.get("display", {}).get("on_screen_keyboard", True))
        self._asr: WhisperEngine | None = None
        self._asr_task: asyncio.Task | None = None
        self._preload_task: asyncio.Task | None = None

    @property
    def voice_output_available(self) -> bool:
        return not isinstance(self.tts, NullTTS)

    async def get_asr(self) -> WhisperEngine:
        """WhisperEngine compartilhado, carregado na primeira chamada (em thread).

        Chamadas concorrentes esperam o mesmo carregamento; cancelar quem espera
        não cancela o carregamento. Levanta SpeechUnavailable em caso de falha
        (e a próxima chamada tenta de novo).
        """
        if self._asr is not None:
            return self._asr
        if self._asr_task is None:
            self._asr_task = asyncio.create_task(asyncio.to_thread(self._load_asr), name="asr-load")
        task = self._asr_task
        try:
            self._asr = await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._asr_task is task:
                self._asr_task = None
            logger.error("Falha ao carregar o Whisper: %s", exc)
            raise SpeechUnavailable(
                "O reconhecimento de voz não pôde ser carregado. Na primeira execução o "
                "modelo Whisper é baixado da internet; confira a conexão."
            ) from exc
        return self._asr

    def preload_asr(self) -> None:
        """Começa a carregar o Whisper sem ninguém esperar. Idempotente; falha só
        vai para o log (quem chamar get_asr() depois tenta de novo)."""
        if self._asr is not None or self._asr_task is not None or self._preload_task is not None:
            return

        async def run() -> None:
            try:
                await self.get_asr()
            except SpeechUnavailable:
                pass  # get_asr() já registrou o motivo

        self._preload_task = asyncio.get_running_loop().create_task(run(), name="asr-preload")
        logger.info("Pré-carregando o reconhecimento de voz.")

    def _load_asr(self) -> WhisperEngine:
        from stt.whisper_engine import WhisperEngine

        stt_cfg = self.settings.get("stt", {})
        return WhisperEngine(
            model_size=stt_cfg.get("whisper_model", "small"),
            device=stt_cfg.get("whisper_device", "cpu"),
            compute_type=stt_cfg.get("whisper_compute_type", "int8"),
            language=stt_cfg.get("language", "pt"),
        )

    def make_recorder(self) -> VoiceRecorder:
        """Gravador novo (o microfone é um recurso do módulo, não compartilhado)."""
        from stt.recorder import VoiceRecorder

        return VoiceRecorder()

    def close(self) -> None:
        """Encerra o que tem thread/processo próprio. Idempotente."""
        if self.llm is not None:
            self.llm.cancel_stream()
        self.tts.stop_speaking()
        self.tts.shutdown()
        for task in (self._preload_task, self._asr_task):
            if task is not None and not task.done():
                task.cancel()
