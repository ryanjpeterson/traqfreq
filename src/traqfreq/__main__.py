"""Entry point: `traqfreq` or `python -m traqfreq`."""

from __future__ import annotations

import uvicorn

from .app import create_app
from .settings import Settings


def main() -> None:
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
