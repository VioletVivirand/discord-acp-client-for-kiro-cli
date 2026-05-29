import logging
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_acp_kiro import bot as bot_module
from discord_acp_kiro.bot import KiroAcpBot
from discord_acp_kiro.config import Config


@pytest.fixture
def bot(monkeypatch):
    cfg = Config("tok", "/tmp", 300, "kiro-cli", "bot.log")
    b = KiroAcpBot(cfg)
    monkeypatch.setattr(bot_module.auth, "whoami", AsyncMock(return_value=True))
    return b


async def test_error_produces_generic_reply_and_logs(bot, monkeypatch, caplog):
    monkeypatch.setattr(bot, "_handle_authed_message", AsyncMock(side_effect=RuntimeError("boom")))
    msg = MagicMock(spec=discord.Message)
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.send = AsyncMock()
    msg.author = MagicMock(bot=False)
    with caplog.at_level(logging.ERROR):
        await bot.on_message(msg)
    msg.channel.send.assert_awaited_once_with("Sorry, something went wrong; please try again.")
    assert any("Unhandled error" in r.message for r in caplog.records)


async def test_close_calls_close_all(bot, monkeypatch):
    close_all = AsyncMock()
    bot.agent_manager.close_all = close_all
    monkeypatch.setattr(discord.Client, "close", AsyncMock())
    await bot.close()
    close_all.assert_awaited_once()
