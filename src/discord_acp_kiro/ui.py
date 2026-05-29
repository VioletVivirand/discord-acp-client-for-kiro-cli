"""Discord UI components for the authentication flow."""
from __future__ import annotations

import asyncio
import logging

import discord

from . import auth
from .auth import LoginOutcome, LoginPrompt

logger = logging.getLogger(__name__)


class LoginCancelView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self._author_id = author_id
        self.cancel_event = asyncio.Event()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self._author_id:
            await interaction.response.send_message("Not your login.", ephemeral=True)
            return
        self.cancel_event.set()
        await interaction.response.defer()
        self.stop()


class LoginModal(discord.ui.Modal, title="Kiro Login"):
    idp_url = discord.ui.TextInput(label="Identity Provider URL", required=True)
    region = discord.ui.TextInput(label="Region", required=False, placeholder="us-east-1", default="us-east-1")

    def __init__(self, bot, original_message: discord.Message):
        super().__init__()
        self._bot = bot
        self._original_message = original_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        region = str(self.region.value).strip() or "us-east-1"
        idp_url = str(self.idp_url.value).strip()
        cancel_view = LoginCancelView(interaction.user.id, timeout=self._bot.config.login_timeout_seconds)
        prompt_message: dict[str, discord.Message] = {}

        async def on_prompt(p: LoginPrompt) -> None:
            msg = await interaction.followup.send(
                f"Visit {p.url} and enter code **{p.code}**", view=cancel_view, wait=True
            )
            prompt_message["msg"] = msg

        outcome = await auth.run_device_flow_login(
            idp_url, region, on_prompt, cancel_view.cancel_event,
            timeout_s=self._bot.config.login_timeout_seconds,
            kiro_cli_bin=self._bot.config.kiro_cli_bin,
        )
        msg = prompt_message.get("msg")
        text = {
            LoginOutcome.SUCCESS: "Authenticated successfully.",
            LoginOutcome.CANCELLED: "Authentication cancelled.",
            LoginOutcome.TIMEOUT: "Authentication failed (timed out).",
            LoginOutcome.FAILED: "Authentication failed.",
        }[outcome]
        if msg is not None:
            await msg.edit(content=text, view=None)
        else:
            await interaction.followup.send(text, ephemeral=True)

        if outcome == LoginOutcome.SUCCESS:
            await self._bot._handle_authed_message(self._original_message)


class AuthView(discord.ui.View):
    def __init__(self, bot, original_message: discord.Message, timeout: float = 300):
        super().__init__(timeout=timeout)
        self._bot = bot
        self._original_message = original_message

    @discord.ui.button(label="Authenticate", style=discord.ButtonStyle.primary)
    async def authenticate(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self._original_message.author.id:
            await interaction.response.send_message("Not your message.", ephemeral=True)
            return
        await interaction.response.send_modal(LoginModal(self._bot, self._original_message))
