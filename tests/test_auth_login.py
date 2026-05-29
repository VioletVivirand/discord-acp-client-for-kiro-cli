import asyncio

import pytest

from discord_acp_kiro import auth
from discord_acp_kiro.auth import LoginOutcome, LoginPrompt


class FakeStdout:
    def __init__(self, lines, delay=0.0, hang=False):
        self._lines = list(lines)
        self._delay = delay
        self._hang = hang

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._delay:
            await asyncio.sleep(self._delay)
        if not self._lines:
            if self._hang:
                await asyncio.sleep(3600)
            raise StopAsyncIteration
        return self._lines.pop(0)


class FakeProc:
    def __init__(self, lines, rc=0, hang=False):
        self.stdout = FakeStdout(lines, hang=hang)
        self._rc = rc
        self.returncode = None
        self._exited = asyncio.Event()
        self.killed = False

    async def wait(self):
        if not self.killed:
            # wait until stdout exhausted naturally for success/fail
            await asyncio.sleep(0.01)
        self.returncode = self._rc
        return self._rc

    def terminate(self):
        self.killed = True
        self.returncode = -15
        self._exited.set()

    def kill(self):
        self.killed = True
        self.returncode = -9


@pytest.fixture
def patch_exec(monkeypatch):
    def _set(proc):
        async def fake_exec(*args, **kwargs):
            return proc
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return _set


SCRIPT = [
    b"Visit the URL to authenticate\n",
    b"https://device.example.com/activate\n",
    b"Enter code: ABCD-1234\n",
]


async def test_success(patch_exec):
    patch_exec(FakeProc(SCRIPT, rc=0))
    prompts = []
    outcome = await auth.run_device_flow_login(
        "https://idp", "us-east-1",
        lambda p: prompts.append(p), asyncio.Event(), timeout_s=5,
    )
    assert outcome == LoginOutcome.SUCCESS
    assert prompts == [LoginPrompt(code="ABCD-1234", url="https://device.example.com/activate")]


async def test_failed(patch_exec):
    patch_exec(FakeProc(SCRIPT, rc=1))
    outcome = await auth.run_device_flow_login(
        "https://idp", "us-east-1", lambda p: None, asyncio.Event(), timeout_s=5,
    )
    assert outcome == LoginOutcome.FAILED


async def test_cancelled(patch_exec):
    patch_exec(FakeProc(SCRIPT, rc=0, hang=True))
    cancel = asyncio.Event()

    async def trigger():
        await asyncio.sleep(0.05)
        cancel.set()

    asyncio.create_task(trigger())
    outcome = await auth.run_device_flow_login(
        "https://idp", "us-east-1", lambda p: None, cancel, timeout_s=5,
    )
    assert outcome == LoginOutcome.CANCELLED


async def test_timeout(patch_exec):
    patch_exec(FakeProc(SCRIPT, rc=0, hang=True))
    outcome = await auth.run_device_flow_login(
        "https://idp", "us-east-1", lambda p: None, asyncio.Event(), timeout_s=0.1,
    )
    assert outcome == LoginOutcome.TIMEOUT


async def test_regex_tolerates_color_codes(patch_exec):
    colored = [
        b"\x1b[32mhttps://device.example.com/activate\x1b[0m\n",
        b"\x1b[1mcode WXYZ-5678\x1b[0m\n",
    ]
    patch_exec(FakeProc(colored, rc=0))
    prompts = []
    await auth.run_device_flow_login(
        "https://idp", "us-east-1", lambda p: prompts.append(p), asyncio.Event(), timeout_s=5,
    )
    assert prompts[0].code == "WXYZ-5678"
    assert prompts[0].url == "https://device.example.com/activate"
