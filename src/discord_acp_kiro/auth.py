"""Kiro CLI authentication helpers."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


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
