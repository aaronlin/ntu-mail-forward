from __future__ import annotations

import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = APP_ROOT / ".env.local"
DEFAULT_STATE_FILE = APP_ROOT / ".local" / "pop3-state.json"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str, default_value: str | None = None) -> str:
    value = os.environ.get(name, default_value)
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def optional_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""
