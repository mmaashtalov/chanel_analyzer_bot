from __future__ import annotations

import asyncio
import os


def main() -> None:
    mode = os.getenv("APP_MODE", "production").strip().lower()
    if mode == "setup":
        from app.setup.server import run_setup_server

        run_setup_server()
        return
    if mode == "demo":
        from app.demo.server import run_demo_server

        run_demo_server()
        return
    if mode != "production":
        raise SystemExit("APP_MODE must be setup, demo or production")

    from app.main import run

    asyncio.run(run())


if __name__ == "__main__":
    main()
