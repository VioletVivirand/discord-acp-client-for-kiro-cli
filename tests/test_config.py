import os

import pytest

from discord_acp_kiro.config import load_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "DISCORD_TOKEN",
        "KIRO_SESSION_CWD",
        "KIRO_IDLE_TIMEOUT_SECONDS",
        "LOGIN_TIMEOUT_SECONDS",
        "KIRO_CLI_BIN",
        "LOG_FILE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_defaults_applied(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    cfg = load_config()
    assert cfg.discord_token == "tok"
    assert cfg.kiro_session_cwd == os.getcwd()
    assert cfg.kiro_idle_timeout_seconds == 300
    assert cfg.login_timeout_seconds == 300
    assert cfg.kiro_cli_bin == "kiro-cli"
    assert cfg.log_file == "bot.log"


def test_values_overridden(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    monkeypatch.setenv("KIRO_SESSION_CWD", "/tmp/work")
    monkeypatch.setenv("KIRO_IDLE_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("LOGIN_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("KIRO_CLI_BIN", "/usr/bin/kiro-cli")
    monkeypatch.setenv("LOG_FILE", "/tmp/x.log")
    cfg = load_config()
    assert cfg.kiro_session_cwd == "/tmp/work"
    assert cfg.kiro_idle_timeout_seconds == 60
    assert cfg.login_timeout_seconds == 120
    assert cfg.kiro_cli_bin == "/usr/bin/kiro-cli"
    assert cfg.log_file == "/tmp/x.log"


def test_missing_token_raises():
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        load_config()
