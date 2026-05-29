"""Transport-agnostic JSON-RPC 2.0 client over NDJSON streams."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

NotificationHandler = Callable[[dict[str, Any]], Awaitable[None] | None]
RequestHandler = Callable[[dict[str, Any]], Awaitable[Any] | Any]


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


class JsonRpcClient:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._reader = reader
        self._writer = writer
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._pending_methods: dict[int, str] = {}
        self._notification_handlers: dict[str, NotificationHandler] = {}
        self._request_handlers: dict[str, RequestHandler] = {}
        self._read_task: asyncio.Task | None = None

    def start(self) -> None:
        self._read_task = asyncio.create_task(self._read_loop())

    def on_notification(self, method: str, handler: NotificationHandler) -> None:
        self._notification_handlers[method] = handler

    def on_request(self, method: str, handler: RequestHandler) -> None:
        self._request_handlers[method] = handler

    async def request(self, method: str, params: Any = None) -> Any:
        self._next_id += 1
        req_id = self._next_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        self._pending_methods[req_id] = method
        await self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        return await fut

    async def notify(self, method: str, params: Any = None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _send(self, msg: dict[str, Any]) -> None:
        self._writer.write((json.dumps(msg) + "\n").encode("utf-8"))
        await self._writer.drain()

    async def _read_loop(self) -> None:
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSON-RPC line: %r", text)
                    continue
                await self._dispatch(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("JSON-RPC read loop error")
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("connection closed"))
            self._pending.clear()

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        if "method" in msg and "id" in msg:
            await self._handle_request(msg)
        elif "method" in msg:
            await self._handle_notification(msg)
        elif "id" in msg:
            self._handle_response(msg)

    def _handle_response(self, msg: dict[str, Any]) -> None:
        fut = self._pending.pop(msg["id"], None)
        method = self._pending_methods.pop(msg["id"], "?")
        if fut is None or fut.done():
            return
        if "error" in msg:
            err = msg["error"]
            logger.warning(
                "JSON-RPC error for %s: code=%s message=%r data=%r",
                method, err.get("code"), err.get("message"), err.get("data"),
            )
            fut.set_exception(JsonRpcError(err.get("code", -1), err.get("message", ""), err.get("data")))
        else:
            fut.set_result(msg.get("result"))

    async def _handle_notification(self, msg: dict[str, Any]) -> None:
        handler = self._notification_handlers.get(msg["method"])
        if handler is None:
            return
        result = handler(msg.get("params") or {})
        if asyncio.iscoroutine(result):
            await result

    async def _handle_request(self, msg: dict[str, Any]) -> None:
        handler = self._request_handlers.get(msg["method"])
        if handler is None:
            await self._send({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32601, "message": "Method not found"},
            })
            return
        try:
            result = handler(msg.get("params") or {})
            if asyncio.iscoroutine(result):
                result = await result
            await self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        except Exception as exc:  # noqa: BLE001
            await self._send({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32603, "message": str(exc)},
            })

    async def close(self) -> None:
        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None
        try:
            self._writer.close()
        except Exception:  # noqa: BLE001
            pass
