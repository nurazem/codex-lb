"""Observe real loopback HTTP boundaries without provider credentials."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from collections.abc import AsyncGenerator, AsyncIterator
from typing import cast

import aiohttp
import pytest
from aiohttp import web

from app.core.clients import proxy
from app.core.clients.upstream_progress import HttpUpstreamProgress
from app.core.openai.requests import ResponsesRequest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["terminal", "json", "partial", "no_headers", "closed", "timeout"])
async def test_http_attempt_retains_structural_progress(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, mode: str
) -> None:
    release = asyncio.Event()
    entered = asyncio.Event()
    first_byte = asyncio.Event()
    terminal = {"id": "resp_test", "status": "completed", "output": []}
    terminal_frame = json.dumps({"type": "response.completed", "response": terminal})
    created_frame = 'data: {"type":"response.created","response":{"id":"resp_test","status":"in_progress"}}\n\n'
    partial = b'data: {"private-payload":"never-log-this"'

    async def handler(request: web.Request) -> web.StreamResponse:
        await request.read()
        entered.set()
        if mode == "no_headers":
            await release.wait()
            return web.Response()
        if mode == "json":
            return web.json_response(terminal)
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        if mode in {"partial", "timeout"}:
            await response.write(partial)
            await release.wait()
        elif mode == "closed":
            await response.write(created_frame.encode())
            await release.wait()
        else:
            await response.write(f"data: {terminal_frame}\n\n".encode())
        return response

    original_chunk = HttpUpstreamProgress.body_chunk

    def observe_chunk(self: HttpUpstreamProgress, size: int) -> None:
        original_chunk(self, size)
        first_byte.set()

    monkeypatch.setattr(HttpUpstreamProgress, "body_chunk", observe_chunk)
    settings = proxy.get_settings().model_copy(
        update={
            "image_inline_fetch_enabled": False,
            "stream_idle_timeout_seconds": 0.1 if mode == "timeout" else 30.0,
            "trace_channels": frozenset(),
        }
    )
    monkeypatch.setattr(proxy, "get_settings", lambda: settings)
    caplog.set_level(logging.INFO, logger="app.core.clients.upstream_progress")
    server = web.Application()
    server.router.add_post("/codex/responses", handler)
    runner = web.AppRunner(server)
    await runner.setup()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.setblocking(False)
    port = listener.getsockname()[1]
    site = web.SockSite(runner, listener)
    await site.start()

    async def consume(stream: AsyncIterator[str]) -> list[str]:
        return [event async for event in stream]

    try:
        async with aiohttp.ClientSession() as session:
            stream = proxy.stream_responses(
                ResponsesRequest.model_validate(
                    {
                        "model": "gpt-5.4",
                        "input": [],
                        "instructions": "private-prompt",
                        "stream": mode != "json",
                    }
                ),
                headers={},
                upstream_stream_transport_override="http",
                access_token="private-token",
                account_id=None,
                base_url=f"http://127.0.0.1:{port}",
                session=session,
            )
            if mode == "closed":
                assert "response.created" in await anext(stream)
                await cast(AsyncGenerator[str, None], stream).aclose()
            elif mode in {"partial", "no_headers"}:
                task = asyncio.create_task(consume(stream))
                try:
                    await asyncio.wait_for(entered.wait() if mode == "no_headers" else first_byte.wait(), 5)
                finally:
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
            else:
                output = await consume(stream)
                assert any(
                    ("response.failed" if mode == "timeout" else "response.completed") in item for item in output
                )
    finally:
        release.set()
        await runner.cleanup()

    records = [
        json.loads(record.getMessage().split(" ", 1)[1])
        for record in caplog.records
        if record.name == "app.core.clients.upstream_progress"
    ]
    assert len(records) <= 5
    assert records[0]["phase"] == "start"
    assert records[-1]["phase"] == "exit"
    assert len({record["attempt_id"] for record in records}) == 1
    final = records[-1]
    assert final["archive_capture_complete"] is None
    assert final["terminal_observed"] is (mode in {"terminal", "json"})
    if mode == "no_headers":
        assert final["headers_ms"] is None
        assert final["received_bytes"] == 0
    else:
        assert final["headers_ms"] is not None
    if mode in {"partial", "timeout"}:
        assert final["received_bytes"] == len(partial)
        assert final["received_events"] == 0
    if mode == "json":
        assert final["received_bytes"] is None
        assert final["first_byte_ms"] is None
    assert final["exit_kind"] == (
        "cancelled"
        if mode in {"partial", "no_headers"}
        else "closed"
        if mode == "closed"
        else "timeout"
        if mode == "timeout"
        else "returned"
    )
    assert "private-" not in json.dumps(records)
    assert "never-log-this" not in json.dumps(records)


@pytest.mark.asyncio
async def test_native_framed_progress_does_not_claim_zero_raw_bytes(caplog: pytest.LogCaptureFixture) -> None:
    from unittest.mock import Mock

    from app.core.clients.native_egress import NativeEgressResponse, SubprocessNativeEgressClient

    events: asyncio.Queue[dict[str, object] | BaseException] = asyncio.Queue()
    block = 'data: {"type":"response.completed","response":{"id":"native-test"}}\n\n'
    events.put_nowait({"type": "sse", "text": block, "more": False})
    events.put_nowait({"type": "end"})
    client = Mock(spec=SubprocessNativeEgressClient)
    response = NativeEgressResponse(
        status=200,
        http_version="HTTP/2",
        headers=(("content-type", "text/event-stream"),),
        client=client,
        request_id="native-test",
        generation=1,
        events=events,
        sse_framed=True,
    )
    progress = HttpUpstreamProgress(body_format="sse")
    caplog.set_level(logging.INFO, logger="app.core.clients.upstream_progress")
    assert [
        event async for event in proxy._iter_sse_events(cast(proxy.SSEResponse, response), 5, 10000, progress=progress)
    ] == [block]
    progress.emit("exit", exit_kind="returned")
    record = json.loads(caplog.records[-1].getMessage().split(" ", 1)[1])
    assert record["received_bytes"] is None
    assert record["first_byte_ms"] is None
    client._finish_request.assert_called_once()
