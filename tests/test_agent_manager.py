import asyncio
import time

import pytest

from discord_acp_kiro.agent_manager import AgentManager
from discord_acp_kiro.agent_session import PromptCallbacks


class StubSession:
    def __init__(self):
        self.last_activity = time.monotonic()
        self.current_turn_task = None
        self.started = False
        self.session_id = None
        self.closed = False
        self.prompts = []
        self.cancelled = 0
        self.loaded = None

    async def start(self):
        self.started = True

    async def new_session(self, cwd):
        self.session_id = "new-sess"
        return self.session_id

    async def load_session(self, sid, cwd):
        self.loaded = sid
        self.session_id = sid

    async def prompt(self, text, callbacks):
        self.prompts.append(text)

    async def cancel(self):
        self.cancelled += 1

    async def close(self):
        self.closed = True


@pytest.fixture
def manager(monkeypatch):
    created = []

    def factory(self):
        s = StubSession()
        created.append(s)
        return s

    monkeypatch.setattr(AgentManager, "_new_session", factory)
    m = AgentManager("/tmp", idle_timeout=300)
    m._created = created
    return m


async def test_get_or_create_caches(manager):
    s1 = await manager.get_or_create(1, existing_session_id=None)
    s2 = await manager.get_or_create(1, existing_session_id=None)
    assert s1 is s2
    assert len(manager._created) == 1
    assert s1.session_id == "new-sess"


async def test_get_or_create_loads_existing(manager):
    s = await manager.get_or_create(1, existing_session_id="abc")
    assert s.loaded == "abc"


async def test_run_prompt_cancels_in_flight(manager):
    s = await manager.get_or_create(1, existing_session_id=None)
    s.current_turn_task = object()
    await manager.run_prompt(1, "hi", PromptCallbacks())
    assert s.cancelled == 1
    assert s.prompts == ["hi"]


async def test_reaper_closes_stale_only(manager):
    fresh = await manager.get_or_create(1, existing_session_id=None)
    stale = await manager.get_or_create(2, existing_session_id=None)
    stale.last_activity = time.monotonic() - 1000
    # run one reap iteration manually
    now = time.monotonic()
    for tid, sess in list(manager._sessions.items()):
        if now - sess.last_activity > manager._idle_timeout:
            await manager.close_thread(tid)
    assert stale.closed is True
    assert fresh.closed is False
    assert 2 not in manager._sessions


async def test_close_all(manager):
    a = await manager.get_or_create(1, existing_session_id=None)
    b = await manager.get_or_create(2, existing_session_id=None)
    await manager.close_all()
    assert a.closed and b.closed
    assert manager._sessions == {}


async def test_rekey(manager):
    s = await manager.get_or_create(100, existing_session_id=None)
    manager.rekey(100, 200)
    assert manager._sessions[200] is s
    assert 100 not in manager._sessions


def test_new_session_receives_model():
    m = AgentManager("/tmp", kiro_model="claude-sonnet-4.5")
    session = m._new_session()
    assert session._model == "claude-sonnet-4.5"
