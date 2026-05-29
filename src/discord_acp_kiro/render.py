"""Output rendering: 2000-char chunking and streaming callbacks."""
from __future__ import annotations

import logging

from .agent_session import PromptCallbacks

logger = logging.getLogger(__name__)

MAX_LEN = 2000


def chunk_text(text: str, limit: int = MAX_LEN) -> list[str]:
    """Split text into <=limit pieces, preferring newline/space boundaries."""
    text = text.strip("\n")
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        split = window.rfind("\n")
        if split == -1:
            split = window.rfind(" ")
        if split <= 0:
            split = limit
        chunks.append(remaining[:split])
        remaining = remaining[split:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


class PromptRenderer:
    """Buffers agent text and renders tool-call messages for one prompt turn."""

    def __init__(self, channel):
        self._channel = channel
        self._buffer: list[str] = []
        self._tool_messages: dict[str, object] = {}

    def callbacks(self) -> PromptCallbacks:
        return PromptCallbacks(
            on_chunk=self._on_chunk,
            on_tool_call=self._on_tool_call,
            on_tool_update=self._on_tool_update,
            on_turn_end=self._on_turn_end,
        )

    def _on_chunk(self, text: str) -> None:
        self._buffer.append(text)

    async def _on_tool_call(self, tool: dict) -> None:
        name = tool.get("title") or tool.get("kind") or "tool"
        msg = await self._channel.send(f"🔧 Running tool: {name}")
        tool_id = tool.get("toolCallId")
        if tool_id is not None:
            self._tool_messages[tool_id] = msg

    async def _on_tool_update(self, update: dict) -> None:
        tool_id = update.get("toolCallId")
        status = update.get("status", "")
        icon = {"completed": "✅", "failed": "❌"}.get(status, "🔧")
        msg = self._tool_messages.get(tool_id)
        name = update.get("title") or "tool"
        content = f"{icon} {name}"
        try:
            if msg is not None:
                await msg.edit(content=content)
            else:
                await self._channel.send(content)
        except Exception:  # noqa: BLE001
            await self._channel.send(content)

    async def _on_turn_end(self) -> None:
        for piece in chunk_text("".join(self._buffer)):
            await self._channel.send(piece)
        self._buffer.clear()
