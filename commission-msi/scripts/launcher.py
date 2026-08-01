"""Lanceur local fiable.

Ordre imposé : ouvrir le port, attendre que le serveur soit prêt, puis
seulement ouvrir le navigateur. Un seul serveur, un seul onglet.

Designed by Prof. Merzoug Mohamed.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

READINESS_TIMEOUT = 90
POLL_INTERVAL = 0.5


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def server_already_running(host: str, port: int) -> bool:
    """Un second lancement ne doit jamais démarrer un deuxième serveur."""
    try:
        with urllib.request.urlopen(  # noqa: S310 - adresse locale uniquement
            f"http://{host}:{port}/api/v1/health", timeout=2
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_until_ready(host: str, port: int, timeout: int = READINESS_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(  # noqa: S310
                f"http://{host}:{port}/api/v1/readiness", timeout=2
            ) as response:
                if response.status == 200 and b'"ready":true' in response.read().replace(b" ", b""):
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(POLL_INTERVAL)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Lanceur local Commission MSI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8731)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "REFUS : cette application ne doit jamais être exposée au réseau. "
            "Seule une écoute sur 127.0.0.1 est autorisée.",
            file=sys.stderr,
        )
        return 2

    if server_already_running(args.host, args.port):
        print(
            f"Un serveur Commission MSI répond déjà sur http://{args.host}:{args.port}. "
            "Aucun second serveur n'est démarré."
        )
        if not args.no_browser:
            webbrowser.open(f"http://{args.host}:{args.port}/", new=0)
        return 0

    if not port_is_free(args.host, args.port):
        print(
            f"ERREUR : le port local {args.port} est occupé par un autre programme.\n"
            f"Fermez ce programme, ou relancez avec un autre port :\n"
            f"    run_windows.bat --port 8732",
            file=sys.stderr,
        )
        return 1

    import uvicorn

    from app.main import app

    config = uvicorn.Config(
        app, host=args.host, port=args.port, log_level="info", access_log=False
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="commission-msi", daemon=True)
    thread.start()

    # Le navigateur n'est ouvert qu'après confirmation de l'état « prêt ».
    if wait_until_ready(args.host, args.port):
        print(f"Commission MSI est prêt : http://{args.host}:{args.port}/")
        if not args.no_browser:
            webbrowser.open(f"http://{args.host}:{args.port}/", new=0)
    else:
        print(
            "ERREUR : le serveur n'a pas atteint l'état « prêt » dans le délai imparti. "
            "Le navigateur n'est pas ouvert. Consultez le journal ci-dessus.",
            file=sys.stderr,
        )
        server.should_exit = True
        thread.join(timeout=10)
        return 3

    try:
        while thread.is_alive():
            thread.join(timeout=1)
    except KeyboardInterrupt:
        print("\nArrêt demandé. Fermeture propre du serveur local…")
        server.should_exit = True
        thread.join(timeout=15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
