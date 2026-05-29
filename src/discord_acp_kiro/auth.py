"""Kiro CLI authentication helpers."""
from __future__ import annotations

import asyncio
import enum
import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# Strip ANSI color codes before matching.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_URL_RE = re.compile(r"https?://\S+")
_CODE_RE = re.compile(r"\b([A-Z0-9]{4,5}-?[A-Z0-9]{4,5})\b")


@dataclass
class LoginPrompt:
    code: str
    url: str


class LoginOutcome(enum.Enum):
    SUCCESS = "success"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    FAILED = "failed"


async def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5)
    except (asyncio.TimeoutError, ProcessLookupError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def run_device_flow_login(
    idp_url: str,
    region: str,
    on_prompt: Callable[[LoginPrompt], Awaitable[None] | None],
    cancel_event: asyncio.Event,
    timeout_s: int = 300,
    kiro_cli_bin: str = "kiro-cli",
) -> LoginOutcome:
    """Drive `kiro-cli login --use-device-flow` and report the outcome."""
    proc = await asyncio.create_subprocess_exec(
        kiro_cli_bin, "login", "--use-device-flow",
        "--identity-provider", idp_url, "--region", region,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def read_stdout() -> int:
        code: str | None = None
        url: str | None = None
        prompted = False
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = _ANSI_RE.sub("", raw.decode("utf-8", errors="replace")).strip()
            if not line:
                continue
            logger.debug("login: %s", line)
            if url is None:
                m = _URL_RE.search(line)
                if m:
                    url = m.group(0)
            if code is None:
                m = _CODE_RE.search(line)
                if m:
                    code = m.group(1)
            if not prompted and code and url:
                prompted = True
                result = on_prompt(LoginPrompt(code=code, url=url))
                if asyncio.iscoroutine(result):
                    await result
        return await proc.wait()

    reader = asyncio.create_task(read_stdout())
    cancel_wait = asyncio.create_task(cancel_event.wait())

    try:
        done, _ = await asyncio.wait(
            {reader, cancel_wait}, timeout=timeout_s, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        pass

    if reader in done:
        cancel_wait.cancel()
        rc = reader.result()
        return LoginOutcome.SUCCESS if rc == 0 else LoginOutcome.FAILED

    # cancelled or timed out
    await _kill(proc)
    reader.cancel()
    outcome = LoginOutcome.CANCELLED if cancel_wait in done else LoginOutcome.TIMEOUT
    cancel_wait.cancel()
    return outcome


async def whoami(kiro_cli_bin: str = "kiro-cli") -> bool:
    """Return True if Kiro CLI reports an authenticated user (exit code 0)."""
    proc = await asyncio.create_subprocess_exec(
        kiro_cli_bin, "whoami",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.debug("whoami failed (%s): %s", proc.returncode, stderr.decode(errors="replace").strip())
        return False
    return True
