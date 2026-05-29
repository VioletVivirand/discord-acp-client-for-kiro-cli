import asyncio

import pytest

from discord_acp_kiro import auth


class FakeProc:
    def __init__(self, returncode, stderr=b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self):
        return b"", self._stderr


@pytest.fixture
def patch_exec(monkeypatch):
    def _set(proc):
        async def fake_exec(*args, **kwargs):
            return proc
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return _set


async def test_whoami_true(patch_exec):
    patch_exec(FakeProc(0))
    assert await auth.whoami() is True


async def test_whoami_false(patch_exec):
    patch_exec(FakeProc(1, b"not logged in"))
    assert await auth.whoami() is False
