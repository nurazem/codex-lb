"""Full private diagnostic boundaries, controlled by conversation archiving."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.conversation_archive import archive_bytes, archive_enabled, archive_json, archive_text


async def archive_stream(stream: AsyncIterator[str], direction: str, capture_id: str) -> AsyncIterator[str]:
    count = 0
    complete = False
    try:
        async for block in stream:
            count += 1
            archive_text(
                direction=direction,
                kind="wire_capture",
                transport="sse",
                text=block,
                extra={"capture_id": capture_id, "ordinal": count},
            )
            yield block
        complete = True
    finally:
        archive_json(
            direction=direction + "_end",
            kind="wire_capture",
            transport="sse",
            payload={"iterator_complete": complete, "events": count, "writer_complete": "unverified"},
            extra={"capture_id": capture_id},
        )


class WireCaptureMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or "responses" not in scope.get("path", "") or not archive_enabled():
            await self.app(scope, receive, send)
            return
        capture_id = uuid4().hex
        extra = {"capture_id": capture_id, "path": scope.get("path", "")}
        archive_json(
            direction="client_request_start",
            kind="wire_capture",
            transport="http",
            payload={"method": scope["method"]},
            headers={k.decode("latin1"): v.decode("latin1") for k, v in scope.get("headers", [])},
            extra=extra,
        )
        request_chunks = response_chunks = 0
        complete = False

        async def observed_receive() -> Message:
            nonlocal request_chunks
            message = await receive()
            if message["type"] == "http.request":
                request_chunks += 1
                archive_bytes(
                    direction="client_request_body",
                    kind="wire_capture",
                    transport="http",
                    data=message.get("body", b""),
                    extra={**extra, "ordinal": request_chunks, "more_body": message.get("more_body", False)},
                )
            return message

        async def observed_send(message: Message) -> None:
            nonlocal response_chunks, complete
            if message["type"] == "http.response.start":
                archive_json(
                    direction="client_response_start",
                    kind="wire_capture",
                    transport="http",
                    payload={"status": message["status"]},
                    extra=extra,
                    headers={k.decode("latin1"): v.decode("latin1") for k, v in message.get("headers", [])},
                )
            elif message["type"] == "http.response.body":
                response_chunks += 1
                archive_bytes(
                    direction="client_response_body",
                    kind="wire_capture",
                    transport="http",
                    data=message.get("body", b""),
                    extra={**extra, "ordinal": response_chunks, "more_body": message.get("more_body", False)},
                )
            await send(message)
            if message["type"] == "http.response.body":
                complete = not message.get("more_body", False)

        try:
            await self.app(scope, observed_receive, observed_send)
        finally:
            archive_json(
                direction="client_request_end",
                kind="wire_capture",
                transport="http",
                payload={
                    "response_complete": complete,
                    "request_chunks": request_chunks,
                    "response_chunks": response_chunks,
                    "writer_complete": "unverified",
                },
                extra=extra,
            )
