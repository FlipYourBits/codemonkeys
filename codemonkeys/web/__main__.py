"""Entry point: python -m codemonkeys.web [--port PORT] [--host HOST]."""

from __future__ import annotations

import argparse
import webbrowser

import uvicorn

from codemonkeys.web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="codemonkeys web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    import os
    app = create_app(cwd=os.getcwd())

    if not args.no_browser:
        url = f"http://{args.host}:{args.port}"

        import threading
        import time

        def _open():
            time.sleep(1)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
