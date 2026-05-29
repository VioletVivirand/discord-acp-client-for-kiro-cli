from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_acp_kiro import bot as bot_module
from discord_acp_kiro.bot import KiroAcpBot
from discord_acp_kiro.config import Config


@pytest.fixture(autouse=True)
def authed(monkeypatch):
    monkeypatch.setattr(bot_module.auth, "whoami", AsyncMock(return_value=True))


@pytest.fixture
def bot():
    cfg = Config("tok", "/tmp", 300, "kiro-cli", "bot.log")
    b = KiroAcpBot(cfg)
    # Give the bot a known identity
    b._connection = MagicMock()
    return b


def _message(channel_cls, *, author_is_bot=False, is_self=False, bot_user=None):
    msg = MagicMock(spec=discord.Message)
    msg.channel = MagicMock(spec=channel_cls)
    msg.channel.send = AsyncMock()
    author = MagicMock()
    author.bot = author_is_bot
    msg.author = bot_user if is_self else author
    return msg


async def test_dm_ignored(bot, monkeypatch):
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.DMChannel)
    await bot.on_message(msg)
    handled.assert_not_called()


async def test_own_message_ignored(bot, monkeypatch):
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    monkeypatch.setattr(type(bot), "user", property(lambda self: "ME"))
    msg = _message(discord.TextChannel, is_self=True, bot_user="ME")
    await bot.on_message(msg)
    handled.assert_not_called()


async def test_bot_author_ignored(bot, monkeypatch):
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.TextChannel, author_is_bot=True)
    await bot.on_message(msg)
    handled.assert_not_called()


async def test_text_channel_handled(bot, monkeypatch):
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.TextChannel)
    await bot.on_message(msg)
    handled.assert_awaited_once_with(msg)


async def test_thread_handled(bot, monkeypatch):
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.Thread)
    await bot.on_message(msg)
    handled.assert_awaited_once_with(msg)


async def test_unauthed_posts_auth_view(bot, monkeypatch):
    monkeypatch.setattr(bot_module.auth, "whoami", AsyncMock(return_value=False))
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.TextChannel)
    await bot.on_message(msg)
    handled.assert_not_called()
    msg.channel.send.assert_awaited_once()
    assert "view" in msg.channel.send.call_args.kwargs
