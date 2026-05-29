import asyncio
import os


async def make_pipe() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """One-directional pipe -> (reader, writer)."""
    loop = asyncio.get_event_loop()
    r_fd, w_fd = os.pipe()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(r_fd, "rb", 0))
    w_transport, w_proto = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, os.fdopen(w_fd, "wb", 0)
    )
    writer = asyncio.StreamWriter(w_transport, w_proto, None, loop)
    return reader, writer
