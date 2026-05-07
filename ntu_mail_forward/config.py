from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = APP_ROOT / ".env.local"
DEFAULT_SETTINGS_FILE = APP_ROOT / "settings.yaml"
DEFAULT_STATE_FILE = APP_ROOT / ".local" / "pop3-state.json"
DEFAULT_ACCOUNTS_ROOT = APP_ROOT / ".local" / "accounts"


@dataclass(frozen=True)
class AccountConfig:
    name: str
    mail_user: str
    mail_password: str
    forward_to: str
    forward_from: str = ""
    pop3_host: str = "msa.ntu.edu.tw"
    pop3_port: int = 995
    smtp_host: str = "smtps.ntu.edu.tw"
    smtp_port: int = 465
    classifier_rules: Path | None = None
    state_file: Path | None = None
    audit_csv: Path | None = None


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


def load_settings_file(path: Path = DEFAULT_SETTINGS_FILE) -> list[AccountConfig]:
    if not path.exists():
        raise SystemExit(
            f"Missing settings file: {path}. Copy settings.yaml.example to settings.yaml."
        )
    try:
        import yaml
    except ImportError:
        raise SystemExit("Missing dependency: install PyYAML to read settings.yaml.") from None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"Invalid YAML in {path}: {exc}") from None
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list) or not accounts:
        raise SystemExit(f"{path} must contain a non-empty accounts list.")

    names: set[str] = set()
    loaded: list[AccountConfig] = []
    for index, payload in enumerate(accounts, start=1):
        if not isinstance(payload, dict):
            raise SystemExit(f"Account #{index} in {path} must be an object.")
        account = _account_from_payload(path, index, payload)
        if account.name in names:
            raise SystemExit(f"Duplicate account name in {path}: {account.name}")
        names.add(account.name)
        loaded.append(account)
    return loaded


load_accounts_file = load_settings_file


def _account_from_payload(path: Path, index: int, payload: dict[str, object]) -> AccountConfig:
    required = ["name", "mail_user", "mail_password", "forward_to"]
    missing = [key for key in required if not _string_value(payload.get(key))]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"Account #{index} in {path} is missing required field(s): {names}")

    name = str(payload["name"])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise SystemExit(
            f"Account #{index} in {path} has invalid name {name!r}; "
            "use letters, numbers, underscores, or hyphens."
        )

    account_root = DEFAULT_ACCOUNTS_ROOT / name
    return AccountConfig(
        name=name,
        mail_user=str(payload["mail_user"]),
        mail_password=str(payload["mail_password"]),
        forward_to=str(payload["forward_to"]),
        forward_from=str(payload.get("forward_from", "") or ""),
        pop3_host=str(payload.get("pop3_host", "") or "msa.ntu.edu.tw"),
        pop3_port=_int_value(payload.get("pop3_port"), "pop3_port", path, index, 995),
        smtp_host=str(payload.get("smtp_host", "") or "smtps.ntu.edu.tw"),
        smtp_port=_int_value(payload.get("smtp_port"), "smtp_port", path, index, 465),
        classifier_rules=_optional_path(path, payload.get("classifier_rules")),
        state_file=_optional_path(path, payload.get("state_file")) or account_root / "pop3-state.json",
        audit_csv=_optional_path(path, payload.get("audit_csv")) or account_root / "audit.csv",
    )


def _string_value(value: object) -> str:
    return value if isinstance(value, str) and value else ""


def _int_value(
    value: object, field_name: str, path: Path, index: int, default_value: int
) -> int:
    if value in (None, ""):
        return default_value
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise SystemExit(
            f"Account #{index} in {path} has invalid integer for {field_name}: {value!r}"
        ) from None
    if parsed <= 0:
        raise SystemExit(
            f"Account #{index} in {path} must use a positive integer for {field_name}."
        )
    return parsed


def _optional_path(config_path: Path, value: object) -> Path | None:
    if not value:
        return None
    if not isinstance(value, str):
        raise SystemExit(f"Path value in {config_path} must be a string: {value!r}")
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return config_path.parent / path
