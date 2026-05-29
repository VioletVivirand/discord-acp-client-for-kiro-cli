"""Discord UI components for the authentication retry flow."""
from __future__ import annotations

import logging

import discord

from . import auth

logger = logging.getLogger(__name__)


class RetryView(discord.ui.View):
    """Offers a Retry button so the user can resend their original message
    once Kiro has been authenticated on the host, without retyping it."""

    def __init__(self, bot, original_message: discord.Message, timeout: float = 600):
        super().__init__(timeout=timeout)
        self._bot = bot
        self._original_message = original_message

    @discord.ui.button(label="Retry", style=discord.ButtonStyle.primary)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self._original_message.author.id:
            await interaction.response.send_message("Not your message.", ephemeral=True)
            return
        if not await auth.whoami(self._bot.config.kiro_cli_bin):
            await interaction.response.send_message(
                "Kiro still isn't authenticated on the host.", ephemeral=True
            )
            return
        await interaction.response.edit_message(content="Retrying…", view=None)
        self.stop()
        await self._bot._handle_authed_message(self._original_message)
