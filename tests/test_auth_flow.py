from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_acp_kiro import ui
from discord_acp_kiro.auth import LoginOutcome, LoginPrompt
from discord_acp_kiro.config import Config


def _bot():
    cfg = Config("tok", "/tmp", 300, 300, "kiro-cli", "bot.log")
    bot = MagicMock()
    bot.config = cfg
    bot._handle_authed_message = AsyncMock()
    return bot


def _interaction(user_id=1):
    inter = MagicMock()
    inter.user.id = user_id
    inter.response.defer = AsyncMock()
    inter.response.send_modal = AsyncMock()
    inter.response.send_message = AsyncMock()
    inter.followup.send = AsyncMock(return_value=MagicMock(edit=AsyncMock()))
    return inter


def _make_modal(bot, original_message):
    modal = ui.LoginModal(bot, original_message)
    modal.idp_url = SimpleNamespace(value="https://idp.example.com")
    modal.region = SimpleNamespace(value="")
    return modal


async def test_authenticate_button_opens_modal():
    bot = _bot()
    original = MagicMock()
    original.author.id = 1
    view = ui.AuthView(bot, original)
    inter = _interaction(user_id=1)
    await view.authenticate.callback(inter)
    inter.response.send_modal.assert_awaited_once()


async def test_authenticate_button_rejects_other_user():
    bot = _bot()
    original = MagicMock()
    original.author.id = 1
    view = ui.AuthView(bot, original)
    inter = _interaction(user_id=999)
    await view.authenticate.callback(inter)
    inter.response.send_modal.assert_not_called()
    inter.response.send_message.assert_awaited_once()


async def test_submit_success_forwards(monkeypatch):
    bot = _bot()
    original = MagicMock()
    captured = {}

    async def fake_login(idp_url, region, on_prompt, cancel_event, **kwargs):
        captured["idp_url"] = idp_url
        captured["region"] = region
        await on_prompt(LoginPrompt(code="ABCD", url="https://x"))
        return LoginOutcome.SUCCESS

    monkeypatch.setattr(ui.auth, "run_device_flow_login", fake_login)
    modal = _make_modal(bot, original)
    inter = _interaction()
    await modal.on_submit(inter)
    assert captured["idp_url"] == "https://idp.example.com"
    assert captured["region"] == "us-east-1"  # blank defaults
    bot._handle_authed_message.assert_awaited_once_with(original)


async def test_submit_failure_does_not_forward(monkeypatch):
    bot = _bot()
    original = MagicMock()

    async def fake_login(idp_url, region, on_prompt, cancel_event, **kwargs):
        await on_prompt(LoginPrompt(code="ABCD", url="https://x"))
        return LoginOutcome.FAILED

    monkeypatch.setattr(ui.auth, "run_device_flow_login", fake_login)
    modal = _make_modal(bot, original)
    inter = _interaction()
    await modal.on_submit(inter)
    bot._handle_authed_message.assert_not_called()
