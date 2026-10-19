"""
Ponto de entrada da plataforma HAI.

    python core/main.py                 # tela cheia, menu principal → módulos
    python core/main.py --windowed      # em janela (desenvolvimento)

Só lê a linha de comando e configura o log; configuração, serviços, menu e
ciclo de vida dos módulos ficam em core/app.py.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HAI - IA na Educação")
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Abre em janela, ignorando [display] fullscreen.",
    )
    parser.add_argument(
        "--tts-backend",
        default=None,
        choices=["piper", "espeak", "pyttsx3"],
        help="Backend de síntese de voz (padrão: [tts] backend do settings.toml).",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Desativa a síntese de voz (respostas só em texto).",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    from core.app import main as run_app

    raise SystemExit(
        run_app(windowed=args.windowed, tts_backend=args.tts_backend, no_tts=args.no_tts)
    )


if __name__ == "__main__":
    main()
