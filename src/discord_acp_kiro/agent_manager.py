"""Per-thread AgentSession lifecycle management."""
from __future__ import annotations

import asyncio
import logging
import time

from .agent_session import AgentSession, PromptCallbacks

logger = logging.getLogger(__name__)


class AgentManager:
    def __init__(self, cwd: str, kiro_cli_bin: str = "kiro-cli", idle_timeout: int = 300, kiro_model: str = "auto"):
        self._cwd = cwd
        self._bin = kiro_cli_bin
        self._idle_timeout = idle_timeout
        self._model = kiro_model
        self._sessions: dict[int, AgentSession] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._reaper_task: asyncio.Task | None = None

    def _lock(self, thread_id: int) -> asyncio.Lock:
        return self._locks.setdefault(thread_id, asyncio.Lock())

    def _new_session(self) -> AgentSession:
        return AgentSession(self._bin, self._model)

    async def get_or_create(self, thread_id: int, *, existing_session_id: str | None) -> AgentSession:
        async with self._lock(thread_id):
            session = self._sessions.get(thread_id)
            if session is not None:
                return session
            session = self._new_session()
            await session.start()
            if existing_session_id is None:
                await session.new_session(self._cwd)
            else:
                await session.load_session(existing_session_id, self._cwd)
            self._sessions[thread_id] = session
            return session

    async def run_prompt(self, thread_id: int, text: str, callbacks: PromptCallbacks) -> None:
        session = self._sessions[thread_id]
        async with self._lock(thread_id):
            if session.current_turn_task is not None:
                await session.cancel()
            await session.prompt(text, callbacks)

    def rekey(self, old_id: int, new_id: int) -> None:
        if old_id in self._sessions:
            self._sessions[new_id] = self._sessions.pop(old_id)
            if old_id in self._locks:
                self._locks[new_id] = self._locks.pop(old_id)

    async def close_thread(self, thread_id: int) -> None:
        session = self._sessions.pop(thread_id, None)
        self._locks.pop(thread_id, None)
        if session is not None:
            await session.close()

    async def start_idle_reaper(self) -> None:
        self._reaper_task = asyncio.create_task(self._reap_loop())

    async def _reap_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                now = time.monotonic()
                stale = [
                    tid for tid, s in self._sessions.items()
                    if now - s.last_activity > self._idle_timeout
                ]
                for tid in stale:
                    logger.info("Reaping idle Kiro session for thread %s", tid)
                    await self.close_thread(tid)
        except asyncio.CancelledError:
            raise

    async def stop(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None

    async def close_all(self) -> None:
        await self.stop()
        sessions = list(self._sessions.values())
        logger.info("Closing %d agent sessions", len(sessions))
        self._sessions.clear()
        self._locks.clear()
        for s in sessions:
            await s.close()
