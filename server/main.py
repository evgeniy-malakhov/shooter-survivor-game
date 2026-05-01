from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal

from server.game_server import GameServer
from shared.difficulty import DIFFICULTY_KEYS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Neon Outbreak async game server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host/IP to bind.")
    parser.add_argument("--port", default=8765, type=int, help="TCP port to bind.")
    parser.add_argument("--difficulty", default="medium", choices=DIFFICULTY_KEYS, help="World difficulty preset.")
    parser.add_argument("--mode", default="survival", choices=("survival", "pvp"), help="Server mode. Use pvp to run without zombies.")
    parser.add_argument("--pvp", action="store_true", help="Shortcut for --mode pvp.")
    parser.add_argument("--profile", action="store_true", help="Print periodic server timing and queue metrics.")
    parser.add_argument("--zombie-workers", type=int, default=None, help="Override the zombie AI decision process count.")
    parser.add_argument("--no-uvloop", action="store_true", help="Disable uvloop even when it is installed.")
    parser.add_argument("--transport", default="tcp", choices=("tcp", "udp"), help="Network transport. UDP is reserved for future work.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.transport == "udp":
        raise SystemExit("UDP transport is planned, but this build currently runs the optimized TCP protocol.")
    _install_uvloop(disabled=args.no_uvloop)
    try:
        asyncio.run(_run_server(args))
    except KeyboardInterrupt:
        print("Server stopped.")


async def _run_server(args: argparse.Namespace) -> None:
    server = GameServer(
        args.host,
        args.port,
        args.difficulty,
        pvp=args.pvp or args.mode == "pvp",
        profile=args.profile,
        zombie_workers=args.zombie_workers,
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(sig, server.request_shutdown, sig.name.lower())
    await server.start()


def _install_uvloop(disabled: bool) -> None:
    if disabled:
        return
    try:
        import uvloop  # type: ignore
    except (ImportError, RuntimeError, OSError):
        return
    with contextlib.suppress(RuntimeError, OSError):
        uvloop.install()


if __name__ == "__main__":
    main()
