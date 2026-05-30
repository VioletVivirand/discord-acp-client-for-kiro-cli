"""Discord bot entry point and message orchestration."""
from __future__ import annotations

import logging

import discord

from . import auth
from .acp_client import JsonRpcError
from .agent_manager import AgentManager
from .agent_session import SessionNotFound
from .config import Config, load_config
from .logging_setup import setup_logging
from .render import PromptRenderer
from .ui import RetryView

logger = logging.getLogger(__name__)


class KiroAcpBot(discord.Client):
    def __init__(self, config: Config, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, **kwargs)
        self.config = config
        self.agent_manager = AgentManager(
            config.kiro_session_cwd, config.kiro_cli_bin,
            config.kiro_idle_timeout_seconds, config.kiro_model,
            config.kiro_agent,
        )

    async def setup_hook(self) -> None:
        await self.agent_manager.start_idle_reaper()

    async def on_ready(self) -> None:
        logger.info("Logged in as %s", self.user)

    async def close(self) -> None:
        await self.agent_manager.close_all()
        await super().close()

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
            return
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return
        if not await auth.whoami(self.config.kiro_cli_bin):
            await message.channel.send(
                "Kiro isn't authenticated on the host. An operator must run "
                "`kiro-cli login` there, then click Retry to resend your message.",
                view=RetryView(self, message),
            )
            return
        try:
            await self._handle_authed_message(message)
        except Exception:  # noqa: BLE001
            logger.exception("Unhandled error handling message")
            try:
                await message.channel.send("Sorry, something went wrong; please try again.")
            except Exception:  # noqa: BLE001
                logger.exception("Failed to send error reply")

    async def _handle_authed_message(self, message: discord.Message) -> None:
        if isinstance(message.channel, discord.Thread):
            await self._handle_thread_message(message)
        else:
            await self._handle_channel_message(message)

    async def _handle_channel_message(self, message: discord.Message) -> None:
        try:
            session = await self.agent_manager.get_or_create(
                message.id, existing_session_id=None
            )
            thread = await message.create_thread(name=session.session_id)
            self.agent_manager.rekey(message.id, thread.id)
            renderer = PromptRenderer(thread)
            async with thread.typing():
                await self.agent_manager.run_prompt(thread.id, message.content, renderer.callbacks())
        except (JsonRpcError, ConnectionError) as exc:
            await self._on_turn_error(message.channel, message.id, exc)

    async def _handle_thread_message(self, message: discord.Message) -> None:
        thread = message.channel
        try:
            await self.agent_manager.get_or_create(
                thread.id, existing_session_id=thread.name
            )
        except SessionNotFound:
            await thread.send(
                "Kiro session no longer exists on disk; please start a new "
                "conversation in a regular channel."
            )
            return
        renderer = PromptRenderer(thread)
        try:
            async with thread.typing():
                await self.agent_manager.run_prompt(thread.id, message.content, renderer.callbacks())
        except (JsonRpcError, ConnectionError) as exc:
            await self._on_turn_error(thread, thread.id, exc)

    async def _on_turn_error(self, channel, thread_id: int, exc: Exception) -> None:
        logger.warning("Kiro turn error: %s", exc)
        await channel.send(f"Kiro error: {exc}")
        await self.agent_manager.close_thread(thread_id)


def main() -> None:
    config = load_config()
    setup_logging(config.log_file)
    bot = KiroAcpBot(config)
    bot.run(config.discord_token, log_handler=None)
