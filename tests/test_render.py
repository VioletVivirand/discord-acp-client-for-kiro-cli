from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_acp_kiro.render import PromptRenderer, chunk_text


def test_chunk_short():
    assert chunk_text("hello") == ["hello"]


def test_chunk_empty():
    assert chunk_text("") == []


def test_chunk_splits_on_newline():
    text = ("a" * 1500) + "\n" + ("b" * 1000)
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert all(len(c) <= 2000 for c in chunks)
    assert chunks[0] == "a" * 1500


def test_chunk_hard_split_no_boundary():
    text = "x" * 4500
    chunks = chunk_text(text)
    assert len(chunks) == 3
    assert all(len(c) <= 2000 for c in chunks)


def _channel():
    ch = MagicMock()
    ch.send = AsyncMock(return_value=MagicMock(edit=AsyncMock()))
    return ch


async def test_text_buffered_and_posted_on_turn_end():
    ch = _channel()
    r = PromptRenderer(ch)
    cb = r.callbacks()
    cb.on_chunk("Hello ")
    cb.on_chunk("world")
    await cb.on_turn_end()
    ch.send.assert_awaited_once_with("Hello world")


async def test_tool_call_message_edited_on_update():
    ch = _channel()
    tool_msg = MagicMock(edit=AsyncMock())
    ch.send = AsyncMock(return_value=tool_msg)
    r = PromptRenderer(ch)
    cb = r.callbacks()
    await cb.on_tool_call({"toolCallId": "t1", "title": "grep"})
    await cb.on_tool_update({"toolCallId": "t1", "status": "completed", "title": "grep"})
    tool_msg.edit.assert_awaited_once()
    assert "✅" in tool_msg.edit.call_args.kwargs["content"]


async def test_large_output_split():
    ch = _channel()
    r = PromptRenderer(ch)
    cb = r.callbacks()
    cb.on_chunk("y" * 4500)
    await cb.on_turn_end()
    assert ch.send.await_count == 3
