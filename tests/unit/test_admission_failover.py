"""Refused fresh admissions fail over to another account instead of surfacing.

Production evidence (2026-11-12): a WebSocket upgrade upstream answered with a
bare 403 ("Invalid response status") was surfaced to the client on the first
attempt for every account-bound Codex body, because the retry loop bound the
body to the refusing account as if it had been dispatched.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from aiohttp.client_reqrep import RequestInfo

import app.core.clients.proxy as proxy_module
from app.core.errors import openai_error
from app.core.openai.requests import ResponsesRequest
from app.modules.proxy import service as proxy_service
from app.modules.proxy.load_balancer import AccountSelection
from tests.unit.test_proxy_utils import (
    _make_account,
    _make_proxy_settings,
    _proxy_error_code,
    _repo_factory,
    _RequestLogsRecorder,
    _SettingsCache,
    _SsePostResponse,
    _SseSession,
)

pytestmark = pytest.mark.unit

# Codex history carries encrypted reasoning, so the body is account-bound once
# it has actually been dispatched to an account.
_ACCOUNT_BOUND_INPUT = [{"type": "reasoning", "id": "rs_bound", "encrypted_content": "owner-bound"}]


def _handshake_rejection() -> proxy_module.ProxyResponseError:
    return proxy_module.ProxyResponseError(
        403,
        openai_error("upstream_error", "Invalid response status"),
        failure_phase="handshake",
        failure_detail="websocket_handshake_rejected",
        upstream_status_code=403,
    )


@pytest.mark.asyncio
async def test_websocket_handshake_rejection_is_marked_undispatched(monkeypatch):
    class Settings:
        upstream_base_url = "https://chatgpt.com/backend-api"
        upstream_connect_timeout_seconds = 8.0
        stream_idle_timeout_seconds = 45.0
        trace_channels = frozenset()
        proxy_request_budget_seconds = 75.0

    request_info = cast(RequestInfo, SimpleNamespace(real_url="wss://chatgpt.com/backend-api/codex/responses"))

    async def fake_open_upstream_websocket(**kwargs):
        raise proxy_module.aiohttp.WSServerHandshakeError(
            request_info, (), status=403, message="Invalid response status"
        )

    monkeypatch.setattr(proxy_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(proxy_module, "_open_upstream_websocket", fake_open_upstream_websocket)
    monkeypatch.setattr(proxy_module, "_maybe_log_upstream_request_start", lambda **kwargs: None)
    monkeypatch.setattr(proxy_module, "_maybe_log_upstream_request_complete", lambda **kwargs: None)

    payload = ResponsesRequest.model_validate({"model": "gpt-5.4", "instructions": "hi", "input": "hi"})

    with pytest.raises(proxy_module.ProxyResponseError) as exc_info:
        _ = [
            event
            async for event in proxy_module.stream_responses(
                payload,
                headers={},
                access_token="token",
                account_id="acc_1",
                session=cast(proxy_module.aiohttp.ClientSession, _SseSession(_SsePostResponse([]))),
                raise_for_status=True,
                upstream_stream_transport_override="websocket",
            )
        ]

    exc = exc_info.value
    assert exc.status_code == 403
    assert _proxy_error_code(exc) == "upstream_error"
    assert exc.failure_phase == proxy_module.WEBSOCKET_HANDSHAKE_FAILURE_PHASE == "handshake"
    assert proxy_module.is_undispatched_upstream_rejection(exc) is True
    assert exc.upstream_status_code == 403
    # A refused upgrade is not a dead proxy route.
    assert proxy_module.is_confirmed_pre_dispatch_transport_error(exc) is False


def test_dispatched_http_rejection_is_not_marked_undispatched():
    dispatched = proxy_module.ProxyResponseError(403, openai_error("upstream_error", "Forbidden"))
    assert proxy_module.is_undispatched_upstream_rejection(dispatched) is False


def _stream_service(monkeypatch, *accounts, fake_stream) -> tuple[proxy_service.ProxyService, AsyncMock]:
    settings = _make_proxy_settings()
    service = proxy_service.ProxyService(_repo_factory(_RequestLogsRecorder()))
    select_account = AsyncMock(
        side_effect=[AccountSelection(account=account, error_message=None) for account in accounts]
        + [AccountSelection(account=None, error_message="No available accounts")] * 4
    )
    monkeypatch.setattr(proxy_service, "get_settings_cache", lambda: _SettingsCache(settings))
    monkeypatch.setattr(proxy_service, "get_settings", lambda: settings)
    monkeypatch.setattr(service._load_balancer, "select_account", select_account)
    monkeypatch.setattr(service._load_balancer, "record_error", AsyncMock())
    monkeypatch.setattr(service._load_balancer, "record_success", AsyncMock())
    monkeypatch.setattr(service, "_ensure_fresh", AsyncMock(side_effect=lambda account, **kwargs: account))
    monkeypatch.setattr(proxy_service, "core_stream_responses", fake_stream)
    return service, select_account


@pytest.mark.asyncio
async def test_account_bound_body_fails_over_after_websocket_handshake_rejection(monkeypatch):
    first = _make_account("acc_handshake_refused")
    second = _make_account("acc_handshake_healthy")
    attempted: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        attempted.append(account_id)
        if account_id == first.chatgpt_account_id:
            raise _handshake_rejection()
        yield 'data: {"type":"response.completed","response":{"id":"resp_after_handshake"}}\n\n'

    service, select_account = _stream_service(monkeypatch, first, second, fake_stream=fake_stream)
    payload = ResponsesRequest.model_validate(
        {"model": "gpt-5.1", "instructions": "", "input": _ACCOUNT_BOUND_INPUT, "stream": True}
    )

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-handshake"})]

    assert attempted == [first.chatgpt_account_id, second.chatgpt_account_id]
    assert select_account.await_count == 2
    assert any("resp_after_handshake" in chunk for chunk in chunks)
    assert not any("Invalid response status" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_account_bound_body_stays_on_owner_after_dispatched_rejection(monkeypatch):
    # Guard: an HTTP 403 from a dispatched POST is still ambiguous and keeps
    # the body on its owner (it is surfaced, never replayed elsewhere).
    first = _make_account("acc_dispatched_refused")
    second = _make_account("acc_dispatched_other")
    attempted: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        attempted.append(account_id)
        if account_id == first.chatgpt_account_id:
            raise proxy_module.ProxyResponseError(403, openai_error("upstream_error", "Forbidden"))
        yield 'data: {"type":"response.completed","response":{"id":"resp_should_not_happen"}}\n\n'
        return

    service, _ = _stream_service(monkeypatch, first, second, fake_stream=fake_stream)
    payload = ResponsesRequest.model_validate(
        {"model": "gpt-5.1", "instructions": "", "input": _ACCOUNT_BOUND_INPUT, "stream": True}
    )

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-dispatched"})]

    assert attempted == [first.chatgpt_account_id]
    assert not any("resp_should_not_happen" in chunk for chunk in chunks)
    failed = [json.loads(chunk.split("data: ", 1)[1]) for chunk in chunks if '"response.failed"' in chunk]
    assert failed and failed[-1]["response"]["error"]["code"] == "upstream_error"


# ---------------------------------------------------------------------------
# HTTP stream: an overload refusal after the lifecycle prelude
# ---------------------------------------------------------------------------


def _sse(payload: dict[str, object]) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


def _created(response_id: str) -> str:
    return _sse({"type": "response.created", "response": {"id": response_id, "status": "in_progress", "output": []}})


def _in_progress(response_id: str) -> str:
    return _sse(
        {"type": "response.in_progress", "response": {"id": response_id, "status": "in_progress", "output": []}}
    )


def _overloaded(response_id: str, **response_fields: object) -> str:
    return _sse(
        {
            "type": "response.failed",
            "response": {
                "id": response_id,
                "status": "failed",
                "output": [],
                "error": {
                    "code": "server_is_overloaded",
                    "message": "Our servers are currently overloaded. Please try again later.",
                },
                **response_fields,
            },
        }
    )


def _completed(response_id: str) -> str:
    return _sse(
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "status": "completed",
                "output": [],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            },
        }
    )


def _events(chunks: list[str]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.mark.asyncio
@pytest.mark.parametrize("prelude", ["created_and_in_progress", "created_only", "none"])
async def test_overload_refusal_before_output_fails_over_to_another_account(monkeypatch, prelude):
    refusing = _make_account("acc_overloaded")
    healthy = _make_account("acc_healthy")
    attempted: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        attempted.append(account_id)
        if account_id == refusing.chatgpt_account_id:
            if prelude != "none":
                yield _created("resp_refused")
            if prelude == "created_and_in_progress":
                yield _in_progress("resp_refused")
            yield _overloaded("resp_refused")
            return
        yield _created("resp_served")
        yield _completed("resp_served")

    service, select_account = _stream_service(monkeypatch, refusing, healthy, fake_stream=fake_stream)
    record_error = AsyncMock()
    monkeypatch.setattr(service._load_balancer, "record_error", record_error)
    payload = ResponsesRequest.model_validate(
        {"model": "gpt-5.1", "instructions": "", "input": _ACCOUNT_BOUND_INPUT, "stream": True}
    )

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-overload"})]
    events = _events(chunks)

    assert attempted == [refusing.chatgpt_account_id, healthy.chatgpt_account_id]
    assert select_account.await_count == 2
    # The second selection excluded the refusing account.
    assert refusing.id in select_account.await_args_list[1].kwargs["exclude_account_ids"]
    # The client never saw the refused response.
    assert "resp_refused" not in "".join(chunks)
    assert [event["type"] for event in events] == ["response.created", "response.completed"]
    assert all(cast(dict[str, object], event["response"])["id"] == "resp_served" for event in events)
    # The refusal still counts against the refusing account's health.
    assert [call.args[0].id for call in record_error.await_args_list] == [refusing.id]


@pytest.mark.asyncio
async def test_overload_refusal_after_output_is_relayed_without_replay(monkeypatch):
    refusing = _make_account("acc_overloaded_late")
    healthy = _make_account("acc_healthy_late")
    attempted: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        attempted.append(account_id)
        yield _created("resp_late")
        yield _sse(
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {"id": "rs_late", "type": "reasoning", "summary": []},
            }
        )
        yield _overloaded("resp_late")

    service, _ = _stream_service(monkeypatch, refusing, healthy, fake_stream=fake_stream)
    payload = ResponsesRequest.model_validate({"model": "gpt-5.1", "instructions": "", "input": "hi", "stream": True})

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-late"})]
    events = _events(chunks)

    assert attempted == [refusing.chatgpt_account_id]
    assert [event["type"] for event in events] == [
        "response.created",
        "response.output_item.added",
        "response.failed",
    ]


@pytest.mark.asyncio
async def test_overload_refusal_reporting_output_tokens_is_not_replayed(monkeypatch):
    refusing = _make_account("acc_overloaded_billed")
    healthy = _make_account("acc_healthy_billed")
    attempted: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        attempted.append(account_id)
        yield _created("resp_billed")
        yield _overloaded("resp_billed", usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8})

    service, _ = _stream_service(monkeypatch, refusing, healthy, fake_stream=fake_stream)
    payload = ResponsesRequest.model_validate({"model": "gpt-5.1", "instructions": "", "input": "hi", "stream": True})

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-billed"})]

    assert attempted == [refusing.chatgpt_account_id]
    assert [event["type"] for event in _events(chunks)] == ["response.created", "response.failed"]


@pytest.mark.asyncio
async def test_bare_server_error_after_prelude_is_not_replayed(monkeypatch):
    # A bare server_error is ambiguous (it is not an explicit refusal): it keeps
    # the existing no-replay contract and the prelude is released unchanged.
    first = _make_account("acc_server_error")
    second = _make_account("acc_server_error_other")
    attempted: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        attempted.append(account_id)
        yield _created("resp_server_error")
        yield _sse(
            {
                "type": "response.failed",
                "response": {
                    "id": "resp_server_error",
                    "status": "failed",
                    "error": {"code": "server_error", "message": "boom"},
                },
            }
        )

    service, _ = _stream_service(monkeypatch, first, second, fake_stream=fake_stream)
    payload = ResponsesRequest.model_validate({"model": "gpt-5.1", "instructions": "", "input": "hi", "stream": True})

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-server-error"})]

    assert attempted == [first.chatgpt_account_id]
    assert [event["type"] for event in _events(chunks)] == ["response.created", "response.failed"]


@pytest.mark.asyncio
async def test_overload_refusal_on_previous_response_owner_is_not_moved(monkeypatch):
    settings = _make_proxy_settings()
    request_logs = _RequestLogsRecorder()
    service = proxy_service.ProxyService(_repo_factory(request_logs))
    owner = _make_account("acc_prev_owner_overloaded")
    other = _make_account("acc_prev_other")
    request_logs.response_owner_by_id[("resp_prev_anchor", None, "sid-owner")] = owner.id
    attempted: list[str | None] = []

    async def fake_select_account(**kwargs):
        if kwargs.get("required_account_id") == owner.id:
            return AccountSelection(account=owner, error_message=None)
        return AccountSelection(account=other, error_message=None)

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False, **kwargs):
        del payload, headers, access_token, base_url, raise_for_status, kwargs
        attempted.append(account_id)
        yield _created("resp_owner_turn")
        yield _overloaded("resp_owner_turn")

    select_account = AsyncMock(side_effect=fake_select_account)
    monkeypatch.setattr(proxy_service, "get_settings_cache", lambda: _SettingsCache(settings))
    monkeypatch.setattr(proxy_service, "get_settings", lambda: settings)
    monkeypatch.setattr(service._load_balancer, "select_account", select_account)
    monkeypatch.setattr(service._load_balancer, "record_error", AsyncMock())
    monkeypatch.setattr(service._load_balancer, "record_success", AsyncMock())
    monkeypatch.setattr(service, "_ensure_fresh", AsyncMock(side_effect=lambda account, **kwargs: account))
    monkeypatch.setattr(proxy_service, "core_stream_responses", fake_stream)

    payload = ResponsesRequest.model_validate(
        {
            "model": "gpt-5.1",
            "instructions": "",
            "input": [],
            "stream": True,
            "previous_response_id": "resp_prev_anchor",
        }
    )

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-owner"})]
    events = _events(chunks)

    # Hard continuity: the turn stays on its owner and the refusal is relayed.
    assert attempted == [owner.chatgpt_account_id]
    assert select_account.await_count == 1
    assert [event["type"] for event in events] == ["response.created", "response.failed"]
    failed = cast(dict[str, object], events[-1]["response"])
    assert cast(dict[str, object], failed["error"])["code"] == "server_is_overloaded"


@pytest.mark.asyncio
async def test_prelude_hold_is_bounded_and_a_late_refusal_is_relayed(monkeypatch):
    # The prelude is released once the hold expires; a refusal after that is
    # accepted work and is relayed without replay.
    from app.modules.proxy._service import support as streaming_helpers

    monkeypatch.setattr(streaming_helpers, "_ADMISSION_PRELUDE_HOLD_SECONDS", 0.05)
    refusing = _make_account("acc_overloaded_slow")
    healthy = _make_account("acc_healthy_slow")
    attempted: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        attempted.append(account_id)
        yield _created("resp_slow")
        await asyncio.sleep(0.3)
        yield _overloaded("resp_slow")

    service, _ = _stream_service(monkeypatch, refusing, healthy, fake_stream=fake_stream)
    payload = ResponsesRequest.model_validate({"model": "gpt-5.1", "instructions": "", "input": "hi", "stream": True})

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-slow"})]

    assert attempted == [refusing.chatgpt_account_id]
    assert [event["type"] for event in _events(chunks)] == ["response.created", "response.failed"]


@pytest.mark.asyncio
async def test_refusal_on_every_account_surfaces_one_terminal_event(monkeypatch):
    first = _make_account("acc_overloaded_a")
    second = _make_account("acc_overloaded_b")
    attempted: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        attempted.append(account_id)
        yield _created(f"resp_{account_id}")
        yield _overloaded(f"resp_{account_id}")

    service, _ = _stream_service(monkeypatch, first, second, fake_stream=fake_stream)
    payload = ResponsesRequest.model_validate({"model": "gpt-5.1", "instructions": "", "input": "hi", "stream": True})

    chunks = [chunk async for chunk in service.stream_responses(payload, {"session_id": "sid-all-refuse"})]
    events = _events(chunks)

    assert attempted == [first.chatgpt_account_id, second.chatgpt_account_id]
    assert [event["type"] for event in events] == ["response.failed"]
    error = cast(dict[str, object], cast(dict[str, object], events[0]["response"])["error"])
    assert error["code"] == "server_is_overloaded"
