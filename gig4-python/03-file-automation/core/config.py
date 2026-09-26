"""Configuration: a TOML file for settings, environment variables for secrets.

Rules:
- Settings (URLs, keywords, folders, limits) live in config.toml. Copy
  config.example.toml to config.toml and edit it.
- Secrets (passwords, API keys, tokens) live ONLY in environment variables or a
  local .env file that is never committed or delivered. Copy .env.example to .env.

Usage:
    from core.config import load_toml, env, load_dotenv_if_present
    load_dotenv_if_present()
    cfg = load_toml("config.toml")
    password = env("SMTP_PASSWORD", required=True)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10: pip install tomli (listed in requirements.txt)
    import tomli as tomllib  # type: ignore[no-redef]


class ConfigError(RuntimeError):
    """A clear, user-facing configuration problem."""


def load_toml(path: str | Path, required: bool = True) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        if required:
            raise ConfigError(
                f"Config file not found: {path}. Copy config.example.toml to {path.name} and edit it."
            )
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc


def load_dotenv_if_present(path: str | Path = ".env") -> bool:
    """Load KEY=VALUE lines from .env into os.environ (existing variables win)."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        from dotenv import load_dotenv  # optional dependency
    except ImportError:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return True
    return load_dotenv(path, override=False)


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise ConfigError(f"Environment variable {name} is not set. Add it to your .env file (see .env.example).")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be a whole number, got {value!r}") from exc
