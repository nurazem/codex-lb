"""ASGI non-streaming collection must own downstream disconnect cleanup."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import select

import app.modules.proxy.api as proxy_api
import app.modules.proxy.service as proxy_service
from app.db.models import RequestLog
from app.db.session import SessionLocal
from app.modules.api_keys.service import ApiKeyUsageReservationData
from tests.integration.test_proxy_responses import _make_auth_json
from tests.integration.test_proxy_websocket_responses import _capability_test_api_key

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/v1/responses", "/backend-api/codex/responses"])
async def test_nonstream_disconnect_stops_upstream_and_settles_once(async_client, app_instance, monkeypatch, route):
    auth = _make_auth_json("acc_nonstream_disconnect", "nonstream-disconnect@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    reservation = ApiKeyUsageReservationData(
        reservation_id="resv_nonstream_disconnect", key_id="key_nonstream_disconnect", model="gpt-5.1"
    )
    started = asyncio.Event()
    closed = asyncio.Event()
    dispatches = []
    settlements = []
    releases = []
    service_releases = []

    async def api_key():
        return _capability_test_api_key(reservation.key_id)

    app_instance.dependency_overrides[proxy_api.validate_proxy_api_key] = api_key

    async def service_release(self, *, api_key, api_key_reservation, request_id):
        service_releases.append(api_key_reservation)
        return True

    async def upstream(*args, **kwargs):
        dispatches.append(True)
        try:
            yield (
                'data: {"type":"response.created","response":{"id":"resp_pending",'
                '"status":"in_progress","output":[]}}\n\n'
            )
            started.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def reserve(*args, **kwargs):
        return reservation

    async def settle(self, api_key, api_key_reservation, settlement, request_id, **kwargs):
        settlements.append((api_key_reservation, settlement.status, settlement.error_code))
        return True

    async def release(*args, **kwargs):
        releases.append(True)

    monkeypatch.setattr(proxy_service, "core_stream_responses", upstream)
    monkeypatch.setattr(proxy_api, "_enforce_request_limits", reserve)
    monkeypatch.setattr(proxy_service.ProxyService, "_settle_stream_api_key_usage", settle)
    monkeypatch.setattr(proxy_api, "_release_reservation", release)
    monkeypatch.setattr(proxy_service.ProxyService, "_release_unsettled_stream_api_key_usage", service_release)
    body = json.dumps({"model": "gpt-5.1", "instructions": "local check", "input": [], "stream": False}).encode()
    sent_body = False

    async def receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}
        await started.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        pass

    invocation = asyncio.create_task(
        app_instance(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": route,
                "raw_path": route.encode(),
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"content-type", b"application/json"),
                    (b"x-request-id", b"req_nonstream_disconnect"),
                ],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        done, _ = await asyncio.wait({invocation}, timeout=1)
        assert done, "Final-response collection ignored downstream disconnect."
        if invocation.cancelled():
            with pytest.raises(asyncio.CancelledError):
                await invocation
        else:
            await invocation
        await asyncio.wait_for(closed.wait(), 1)
        await app_instance.state.proxy_service.drain_persistence_tasks(timeout_seconds=5)
        assert dispatches == [True]
        assert settlements == []
        assert service_releases == [reservation]
        assert releases == []
        async with SessionLocal() as session:
            records = (
                (
                    await session.execute(
                        select(RequestLog).where(RequestLog.archive_request_id == "req_nonstream_disconnect")
                    )
                )
                .scalars()
                .all()
            )
            assert len(records) == 1
            assert records[0].status == "cancelled"
            assert records[0].error_code == "client_disconnected"
    finally:
        app_instance.dependency_overrides.pop(proxy_api.validate_proxy_api_key, None)
        if not invocation.done():
            invocation.cancel()
        await asyncio.gather(invocation, return_exceptions=True)
