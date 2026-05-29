import asyncio

import pytest

from discord_acp_kiro.acp_client import JsonRpcClient
from discord_acp_kiro.agent_session import AgentSession, PromptCallbacks, SessionNotFound

from .conftest import make_pipe


class FakeAgent:
    """Minimal ACP agent over JSON-RPC for driving AgentSession."""

    def __init__(self, client: JsonRpcClient):
        self.client = client
        self.prompt_updates: list[dict] = []
        self.load_fails = False
        client.on_request("initialize", lambda p: {"protocolVersion": 1})
        client.on_request("session/new", lambda p: {"sessionId": "sess-123"})
        client.on_request("session/load", self._load)
        client.on_request("session/prompt", self._prompt)
        client.on_notification("session/cancel", lambda p: None)

    def _load(self, params):
        if self.load_fails:
            from discord_acp_kiro.acp_client import JsonRpcError
            raise JsonRpcError(-32000, "session not found")
        return {}

    async def _prompt(self, params):
        for upd in self.prompt_updates:
            await self.client.notify("session/update", {"sessionId": params["sessionId"], "update": upd})
        return {"stopReason": "end_turn"}


@pytest.fixture
async def session_with_agent():
    s_reader, a_writer = await make_pipe()
    a_reader, s_writer = await make_pipe()
    agent = FakeAgent(JsonRpcClient(a_reader, a_writer))
    agent.client.start()
    session = AgentSession()
    session._attach_client(s_reader, s_writer)
    yield session, agent
    await session.close()
    await agent.client.close()


async def test_initialize_and_new_session(session_with_agent):
    session, agent = session_with_agent
    await session._initialize()
    sid = await session.new_session("/tmp")
    assert sid == "sess-123"


async def test_load_session_happy(session_with_agent):
    session, agent = session_with_agent
    await session.load_session("sess-xyz", "/tmp")
    assert session.session_id == "sess-xyz"


async def test_load_session_not_found(session_with_agent):
    session, agent = session_with_agent
    agent.load_fails = True
    with pytest.raises(SessionNotFound):
        await session.load_session("missing", "/tmp")


async def test_prompt_invokes_callbacks(session_with_agent):
    session, agent = session_with_agent
    await session.new_session("/tmp")
    agent.prompt_updates = [
        {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Hello"}},
        {"sessionUpdate": "tool_call", "toolCallId": "t1", "title": "grep"},
        {"sessionUpdate": "tool_call_update", "toolCallId": "t1", "status": "completed"},
    ]
    chunks, tool_calls, tool_updates, ended = [], [], [], []
    cb = PromptCallbacks(
        on_chunk=lambda t: chunks.append(t),
        on_tool_call=lambda u: tool_calls.append(u),
        on_tool_update=lambda u: tool_updates.append(u),
        on_turn_end=lambda: ended.append(True),
    )
    await session.prompt("hi", cb)
    await asyncio.sleep(0.05)
    assert chunks == ["Hello"]
    assert len(tool_calls) == 1
    assert len(tool_updates) == 1
    assert ended == [True]


async def test_close_idempotent(session_with_agent):
    session, agent = session_with_agent
    await session.close()
    await session.close()  # no raise
