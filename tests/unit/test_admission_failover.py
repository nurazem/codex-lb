"""Refused fresh admissions fail over to another account instead of surfacing.

Production evidence (2026-11-12): a WebSocket upgrade upstream answered with a
bare 403 ("Invalid response status") was surfaced to the client on the first
attempt for every account-bound Codex body, because the retry loop bound the
body to the refusing account as if it had been dispatched.
"""

from __future__ import annotations

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
