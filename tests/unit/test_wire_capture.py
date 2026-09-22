from __future__ import annotations

import base64
import json

import pytest

from app.core import conversation_archive, wire_capture
from app.modules.proxy.api import _normalize_public_responses_stream


@pytest.fixture
def captured(monkeypatch):
    records = []
    monkeypatch.setattr(conversation_archive, "archive_enabled", lambda: True)
    monkeypatch.setattr(wire_capture, "archive_enabled", lambda: True)
    monkeypatch.setattr(conversation_archive, "_enqueue_record", lambda path, record: records.append(record))
    return records


async def test_wire_capture_preserves_body_and_redacts_credentials(captured):
    async def app(scope, receive, send):
        assert (await receive())["body"] == b'{"input":"private prompt","tool":"private result"}'
        await send({"type": "http.response.start", "status": 200, "headers": [(b"set-cookie", b"secret")]})
        await send({"type": "http.response.body", "body": b"data: exact-stream\n\n", "more_body": False})

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/responses",
        "headers": [(b"authorization", b"Bearer secret")],
    }

    async def receive():
        return {"type": "http.request", "body": b'{"input":"private prompt","tool":"private result"}'}

    sent = []

    async def send(message):
        sent.append(message)

    await wire_capture.WireCaptureMiddleware(app)(scope, receive, send)
    assert sent[-1]["body"] == b"data: exact-stream\n\n"
    assert captured[0]["headers"]["authorization"] == "[redacted]"
    bodies = [r for r in captured if r["direction"] == "client_request_body"]
    assert b"private prompt" in base64.b64decode(bodies[0]["payload"]["data"])
    assert captured[-1]["payload"]["response_complete"] is True
    assert "secret" not in json.dumps(captured)


async def test_normalizer_retains_both_boundaries_and_shifted_index(captured):
    async def source():
        for event in [
            {"type": "response.created", "response": {"id": "resp_test", "status": "in_progress", "output": []}},
            {
                "type": "response.output_item.added",
                "output_index": 7,
                "item": {
                    "id": "fn_test",
                    "type": "function_call",
                    "call_id": "call_test",
                    "name": "tool",
                    "arguments": "",
                    "status": "in_progress",
                },
            },
            {
                "type": "response.function_call_arguments.done",
                "output_index": 10,
                "item_id": "fn_test",
                "arguments": "{}",
            },
            {"type": "response.completed", "response": {"id": "resp_test", "status": "completed", "output": []}},
        ]:
            yield "data: " + json.dumps(event) + "\n\n"

    output = [block async for block in _normalize_public_responses_stream(source())]
    assert any('"output_index":10' in block.replace(" ", "") for block in output)
    for direction in ("normalizer_input", "normalizer_output"):
        records = [r for r in captured if r["direction"] == direction]
        assert any('"output_index":10' in r["payload"]["text"].replace(" ", "") for r in records)
        end = next(r for r in captured if r["direction"] == direction + "_end")
        assert end["payload"]["iterator_complete"]
        assert end["payload"]["events"] == len(records)
