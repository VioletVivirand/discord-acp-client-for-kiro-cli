"""High-level wrapper around one `kiro-cli acp` subprocess."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .acp_client import JsonRpcClient, JsonRpcError

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):
    pass


@dataclass
class PromptCallbacks:
    on_chunk: Callable[[str], Awaitable[None] | None] | None = None
    on_tool_call: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None
    on_tool_update: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None
    on_turn_end: Callable[[], Awaitable[None] | None] | None = None


async def _maybe_await(result: Any) -> None:
    if asyncio.iscoroutine(result):
        await result


class AgentSession:
    def __init__(self, kiro_cli_bin: str = "kiro-cli"):
        self._bin = kiro_cli_bin
        self._proc: asyncio.subprocess.Process | None = None
        self._client: JsonRpcClient | None = None
        self.session_id: str | None = None
        self.last_activity: float = time.monotonic()
        self.current_turn_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            self._bin, "acp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        asyncio.create_task(self._drain_stderr(self._proc.stderr))
        self._attach_client(self._proc.stdout, self._proc.stdin)
        await self._initialize()

    async def _drain_stderr(self, reader: asyncio.StreamReader) -> None:
        while True:
            line = await reader.readline()
            if not line:
                break
            logger.warning("kiro-cli acp stderr: %s", line.decode("utf-8", "replace").rstrip())

    def _attach_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._client = JsonRpcClient(reader, writer)
        self._client.start()

    async def _initialize(self) -> None:
        self._bump()
        await self._client.request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {},
        })

    def _bump(self) -> None:
        self.last_activity = time.monotonic()

    async def new_session(self, cwd: str) -> str:
        self._bump()
        result = await self._client.request("session/new", {"cwd": cwd, "mcpServers": []})
        self.session_id = result["sessionId"]
        return self.session_id

    async def load_session(self, session_id: str, cwd: str) -> None:
        self._bump()
        try:
            await self._client.request("session/load", {"sessionId": session_id, "cwd": cwd, "mcpServers": []})
        except JsonRpcError as exc:
            if "not found" in exc.message.lower():
                raise SessionNotFound(session_id) from exc
            raise
        self.session_id = session_id

    async def prompt(self, text: str, callbacks: PromptCallbacks) -> None:
        self._bump()
        turn_done = asyncio.get_event_loop().create_future()

        async def on_update(params: dict[str, Any]) -> None:
            update = params.get("update", {})
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = update.get("content", {})
                if callbacks.on_chunk and content.get("type") == "text":
                    await _maybe_await(callbacks.on_chunk(content.get("text", "")))
            elif kind == "tool_call":
                if callbacks.on_tool_call:
                    await _maybe_await(callbacks.on_tool_call(update))
            elif kind == "tool_call_update":
                if callbacks.on_tool_update:
                    await _maybe_await(callbacks.on_tool_update(update))

        self._client.on_notification("session/update", on_update)

        async def run() -> None:
            await self._client.request("session/prompt", {
                "sessionId": self.session_id,
                "prompt": [{"type": "text", "text": text}],
            })
            if not turn_done.done():
                turn_done.set_result(None)

        self.current_turn_task = asyncio.create_task(run())
        try:
            await self.current_turn_task
        finally:
            self.current_turn_task = None
            self._bump()
        if callbacks.on_turn_end:
            await _maybe_await(callbacks.on_turn_end())

    async def cancel(self) -> None:
        self._bump()
        if self.session_id is not None and self._client is not None:
            try:
                await self._client.notify("session/cancel", {"sessionId": self.session_id})
            except Exception:  # noqa: BLE001
                logger.debug("cancel notify failed", exc_info=True)
        task = self.current_turn_task
        if task is not None:
            try:
                await task
            except Exception:  # noqa: BLE001
                pass

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        proc = self._proc
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        self._proc = None
