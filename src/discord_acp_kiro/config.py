"""Configuration loading from environment."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    discord_token: str
    kiro_session_cwd: str
    kiro_idle_timeout_seconds: int
    kiro_cli_bin: str
    kiro_model: str
    log_file: str


def load_config() -> Config:
    """Load configuration from environment (and a .env file if present).

    Raises ValueError if DISCORD_TOKEN is missing.
    """
    load_dotenv()

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN is required but not set")

    return Config(
        discord_token=token,
        kiro_session_cwd=os.environ.get("KIRO_SESSION_CWD") or os.getcwd(),
        kiro_idle_timeout_seconds=int(os.environ.get("KIRO_IDLE_TIMEOUT_SECONDS", "300")),
        kiro_cli_bin=os.environ.get("KIRO_CLI_BIN", "kiro-cli"),
        kiro_model=os.environ.get("KIRO_MODEL", "auto"),
        log_file=os.environ.get("LOG_FILE", "bot.log"),
    )
