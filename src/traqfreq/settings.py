"""Settings read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    legacy_db: Path | None
    port: int
    host: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        legacy = env.get("TRAQFREQ_LEGACY_DB") or None
        return cls(
            data_dir=Path(env.get("TRAQFREQ_DATA_DIR", "./data")),
            legacy_db=Path(legacy) if legacy else None,
            port=int(env.get("TRAQFREQ_PORT", "4491")),
            host=env.get("TRAQFREQ_HOST", "0.0.0.0"),
        )
