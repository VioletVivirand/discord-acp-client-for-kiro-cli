from unittest.mock import AsyncMock, MagicMock

from discord_acp_kiro import ui
from discord_acp_kiro.config import Config


def _bot(authed: bool):
    bot = MagicMock()
    bot.config = Config("tok", "/tmp", 300, "kiro-cli", "auto", None, "bot.log")
    bot._handle_authed_message = AsyncMock()
    return bot


def _interaction(user_id=1):
    inter = MagicMock()
    inter.user.id = user_id
    inter.response.send_message = AsyncMock()
    inter.response.edit_message = AsyncMock()
    return inter


def _view(bot):
    original = MagicMock()
    original.author.id = 1
    return ui.RetryView(bot, original), original


async def test_retry_rejects_other_user():
    view, _ = _view(_bot(True))
    inter = _interaction(user_id=999)
    await view.retry.callback(inter)
    inter.response.send_message.assert_awaited_once()


async def test_retry_still_unauthed(monkeypatch):
    bot = _bot(False)
    monkeypatch.setattr(ui.auth, "whoami", AsyncMock(return_value=False))
    view, _ = _view(bot)
    inter = _interaction()
    await view.retry.callback(inter)
    inter.response.send_message.assert_awaited_once()
    bot._handle_authed_message.assert_not_called()


async def test_retry_authed_forwards(monkeypatch):
    bot = _bot(True)
    monkeypatch.setattr(ui.auth, "whoami", AsyncMock(return_value=True))
    view, original = _view(bot)
    inter = _interaction()
    await view.retry.callback(inter)
    inter.response.edit_message.assert_awaited_once()
    bot._handle_authed_message.assert_awaited_once_with(original)
