from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_acp_kiro import bot as bot_module
from discord_acp_kiro.acp_client import JsonRpcError
from discord_acp_kiro.agent_session import SessionNotFound
from discord_acp_kiro.bot import KiroAcpBot
from discord_acp_kiro.config import Config


@pytest.fixture
def bot():
    cfg = Config("tok", "/tmp", 300, "kiro-cli", "auto", None, "bot.log")
    b = KiroAcpBot(cfg)
    b.agent_manager = MagicMock()
    b.agent_manager.get_or_create = AsyncMock()
    b.agent_manager.run_prompt = AsyncMock()
    b.agent_manager.rekey = MagicMock()
    b.agent_manager.close_thread = AsyncMock()
    return b


async def test_channel_message_creates_thread_and_prompts(bot):
    session = MagicMock()
    session.session_id = "sess-abc"
    bot.agent_manager.get_or_create.return_value = session
    thread = MagicMock()
    thread.id = 555
    msg = MagicMock(spec=discord.Message)
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.id = 111
    msg.content = "hi"
    msg.create_thread = AsyncMock(return_value=thread)
    await bot._handle_channel_message(msg)
    msg.create_thread.assert_awaited_once_with(name="sess-abc")
    bot.agent_manager.rekey.assert_called_once_with(111, 555)
    bot.agent_manager.run_prompt.assert_awaited_once()
    assert bot.agent_manager.run_prompt.call_args.args[0] == 555


async def test_thread_message_loads_session(bot):
    msg = MagicMock(spec=discord.Message)
    thread = MagicMock(spec=discord.Thread)
    thread.id = 777
    thread.name = "sess-xyz"
    thread.send = AsyncMock()
    msg.channel = thread
    msg.content = "more"
    await bot._handle_thread_message(msg)
    bot.agent_manager.get_or_create.assert_awaited_once_with(777, existing_session_id="sess-xyz")
    bot.agent_manager.run_prompt.assert_awaited_once()


async def test_thread_session_not_found(bot):
    bot.agent_manager.get_or_create.side_effect = SessionNotFound("x")
    msg = MagicMock(spec=discord.Message)
    thread = MagicMock(spec=discord.Thread)
    thread.id = 1
    thread.name = "gone"
    thread.send = AsyncMock()
    msg.channel = thread
    msg.content = "x"
    await bot._handle_thread_message(msg)
    thread.send.assert_awaited_once()
    assert "no longer exists" in thread.send.call_args.args[0]
    bot.agent_manager.run_prompt.assert_not_called()


async def test_mid_turn_error_closes_thread(bot):
    msg = MagicMock(spec=discord.Message)
    thread = MagicMock(spec=discord.Thread)
    thread.id = 9
    thread.name = "sess"
    thread.send = AsyncMock()
    msg.channel = thread
    msg.content = "x"
    bot.agent_manager.run_prompt.side_effect = JsonRpcError(-32000, "boom")
    await bot._handle_thread_message(msg)
    thread.send.assert_awaited()
    assert "Kiro error" in thread.send.call_args.args[0]
    bot.agent_manager.close_thread.assert_awaited_once_with(9)
