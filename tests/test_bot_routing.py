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
    cfg = Config("tok", "/tmp", 300, "kiro-cli", "auto", None, "bot.log")
    b = KiroAcpBot(cfg)
    # Give the bot a known identity
    b._connection = MagicMock()
    return b


def _channel(channel_cls, *, private=True):
    """Build a mock channel reporting the given @everyone visibility.

    For Thread, the parent TextChannel carries the visibility.
    """
    perms = MagicMock()
    perms.view_channel = not private

    def _make(cls):
        ch = MagicMock(spec=cls)
        ch.permissions_for = MagicMock(return_value=perms)
        ch.guild = MagicMock()
        ch.send = AsyncMock()
        return ch

    if channel_cls is discord.Thread:
        thread = _make(discord.Thread)
        thread.parent = _make(discord.TextChannel)
        return thread
    return _make(channel_cls)


def _message(channel_cls, *, author_is_bot=False, is_self=False, bot_user=None,
             msg_type=discord.MessageType.default, private=True):
    msg = MagicMock(spec=discord.Message)
    msg.type = msg_type
    msg.channel = _channel(channel_cls, private=private)
    author = MagicMock()
    author.bot = author_is_bot
    msg.author = bot_user if is_self else author
    return msg


def test_is_private_text_channel_private():
    assert bot_module._is_private_channel(_channel(discord.TextChannel, private=True))


def test_is_private_text_channel_public():
    assert not bot_module._is_private_channel(_channel(discord.TextChannel, private=False))


def test_is_private_thread_private_parent():
    assert bot_module._is_private_channel(_channel(discord.Thread, private=True))


def test_is_private_thread_public_parent():
    assert not bot_module._is_private_channel(_channel(discord.Thread, private=False))


def test_is_private_thread_no_parent():
    thread = MagicMock(spec=discord.Thread)
    thread.parent = None
    assert not bot_module._is_private_channel(thread)


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


async def test_public_channel_ignored(bot, monkeypatch):
    whoami = AsyncMock(return_value=True)
    monkeypatch.setattr(bot_module.auth, "whoami", whoami)
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.TextChannel, private=False)
    await bot.on_message(msg)
    handled.assert_not_called()
    whoami.assert_not_called()


async def test_public_thread_ignored(bot, monkeypatch):
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.Thread, private=False)
    await bot.on_message(msg)
    handled.assert_not_called()


async def test_system_message_ignored(bot, monkeypatch):
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.TextChannel, msg_type=discord.MessageType.pins_add)
    await bot.on_message(msg)
    handled.assert_not_called()


async def test_unauthed_posts_auth_view(bot, monkeypatch):
    monkeypatch.setattr(bot_module.auth, "whoami", AsyncMock(return_value=False))
    handled = AsyncMock()
    monkeypatch.setattr(bot, "_handle_authed_message", handled)
    msg = _message(discord.TextChannel)
    await bot.on_message(msg)
    handled.assert_not_called()
    msg.channel.send.assert_awaited_once()
    assert "view" in msg.channel.send.call_args.kwargs
