"""
Ponto de entrada da plataforma HAI.

    python core/main.py                 # interface gráfica: menu principal → módulos
    python core/main.py --windowed      # idem, em janela (sem tela cheia)
    python core/main.py --terminal      # modo terminal legado (VAD), sem interface
    python core/main.py --ptt           # modo terminal com Push-to-Talk (Enter)

A interface gráfica (core/app.py) abre o menu com os módulos de modules/;
o modo terminal (core/terminal.py) é o tutor por voz original. Os dois usam
os mesmos serviços (core/services.py).
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HAI — IA na Educação")
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="Modo terminal (sem interface gráfica): conversa por voz com VAD.",
    )
    parser.add_argument(
        "--ptt",
        action="store_true",
        help="Modo terminal com Push-to-Talk (Enter para gravar/parar). Implica --terminal.",
    )
    parser.add_argument(
        "--allow-barge-in",
        action="store_true",
        help="Modo terminal: mantém o microfone capturando enquanto o tutor responde "
        "(o padrão é pausar o mic durante cada resposta). Implica --terminal.",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Interface gráfica em janela, ignorando [display] fullscreen.",
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
    args = parser.parse_args(argv)
    args.terminal = args.terminal or args.ptt or args.allow_barge_in
    return args


async def run_gui(args: argparse.Namespace) -> int:
    from core.app import App, DisplayUnavailable
    from core.services import Services, load_config
    from modules import build_modules

    settings, secrets, problems = load_config()
    for problem in problems:
        logger.warning(problem)
    services = Services(
        settings,
        secrets,
        tts_backend=args.tts_backend,
        no_tts=args.no_tts,
        config_problems=problems,
    )
    display_cfg = settings.get("display", {})
    app = App(
        services,
        build_modules(services),
        fullscreen=display_cfg.get("fullscreen", True) and not args.windowed,
        width=display_cfg.get("width", 1024),
        height=display_cfg.get("height", 600),
    )
    try:
        await app.run()
    except DisplayUnavailable as exc:
        services.close()
        print(
            f"Não foi possível abrir a interface gráfica ({exc}).\n"
            "Verifique se há uma sessão gráfica ($DISPLAY) e o pacote python3-tk, ou use\n"
            "    python core/main.py --terminal",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> None:
    args = parse_args()
    try:
        if args.terminal:
            from core.terminal import run_terminal

            asyncio.run(
                run_terminal(
                    ptt=args.ptt,
                    tts_backend=args.tts_backend,
                    no_tts=args.no_tts,
                    allow_barge_in=args.allow_barge_in,
                )
            )
        else:
            raise SystemExit(asyncio.run(run_gui(args)))
    except KeyboardInterrupt:
        print("\nEncerrando o programa.")


if __name__ == "__main__":
    main()
