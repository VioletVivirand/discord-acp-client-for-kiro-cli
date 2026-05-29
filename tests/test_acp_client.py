import asyncio
import os

import pytest

from discord_acp_kiro.acp_client import JsonRpcClient, JsonRpcError


async def _make_pipe() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """One-directional pipe -> (reader, writer)."""
    loop = asyncio.get_event_loop()
    r_fd, w_fd = os.pipe()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(r_fd, "rb", 0))
    w_transport, w_proto = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, os.fdopen(w_fd, "wb", 0))
    writer = asyncio.StreamWriter(w_transport, w_proto, None, loop)
    return reader, writer


@pytest.fixture
async def client_pair():
    """Returns (client, agent) JsonRpcClients connected back to back."""
    c_reader, a_writer = await _make_pipe()  # agent -> client
    a_reader, c_writer = await _make_pipe()  # client -> agent
    client = JsonRpcClient(c_reader, c_writer)
    agent = JsonRpcClient(a_reader, a_writer)
    client.start()
    agent.start()
    yield client, agent
    await client.close()
    await agent.close()


async def test_request_response_roundtrip(client_pair):
    client, agent = client_pair
    agent.on_request("ping", lambda params: {"pong": params.get("v")})
    result = await client.request("ping", {"v": 42})
    assert result == {"pong": 42}


async def test_concurrent_requests_correlate(client_pair):
    client, agent = client_pair

    async def handler(params):
        await asyncio.sleep(0.01 * params["d"])
        return params["d"]

    agent.on_request("echo", handler)
    results = await asyncio.gather(
        client.request("echo", {"d": 3}),
        client.request("echo", {"d": 1}),
        client.request("echo", {"d": 2}),
    )
    assert results == [3, 1, 2]


async def test_notification_dispatch(client_pair):
    client, agent = client_pair
    seen = asyncio.get_event_loop().create_future()
    client.on_notification("evt", lambda params: seen.set_result(params))
    await agent.notify("evt", {"x": 1})
    assert await asyncio.wait_for(seen, 1) == {"x": 1}


async def test_unknown_request_returns_method_not_found(client_pair):
    client, agent = client_pair
    with pytest.raises(JsonRpcError) as exc:
        await client.request("fs/read", {})
    assert exc.value.code == -32601


async def test_close_cancels_read_task(client_pair):
    client, agent = client_pair
    await client.close()
    assert client._read_task is None


async def test_malformed_line_skipped(client_pair):
    client, agent = client_pair
    agent.on_request("ping", lambda params: "ok")
    # inject a malformed line directly through the agent's writer
    agent._writer.write(b"not json\n")
    await agent._writer.drain()
    # client should still work
    result = await client.request("ping")
    assert result == "ok"
