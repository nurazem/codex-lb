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


@pytest.mark.asyncio
async def test_nonstream_mixed_requests_release_configured_account_capacity(async_client, app_instance, monkeypatch):
    """Exercise the deployment's 4-create/8-stream caps with twelve callers."""
    from collections import Counter

    import app.modules.proxy.load_balancer as balancer_module
    from app.modules.proxy._service.streaming import retry as retry_module

    # Upstream now waits for local capacity instead of returning immediately.
    # Keep that path but compress its deliberate wall-clock backoff in this test.
    recovery_sleep = retry_module._account_selection_recovery_sleep_seconds
    monkeypatch.setattr(
        retry_module,
        "_account_selection_recovery_sleep_seconds",
        lambda selection: 0.01 if recovery_sleep(selection) is not None else None,
    )
    from app.core.config.settings import Settings

    account_id = "acc_nonstream_mixed"
    auth = _make_auth_json(account_id, "mixed-capacity@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    settings = Settings(
        http_responses_session_bridge_enabled=False,
        proxy_request_budget_seconds=600,
        proxy_response_create_limit=256,
        proxy_account_response_create_limit=4,
        proxy_account_stream_limit=8,
    )
    monkeypatch.setattr(proxy_service, "get_settings", lambda: settings)
    monkeypatch.setattr(balancer_module, "get_settings", lambda: settings)
    assert (
        proxy_service.effective_account_concurrency_caps(await proxy_service.get_settings_cache().get()).stream_limit
        == 8
    )
    dispatched = Counter()
    active = set()
    peak = 0
    saturated = asyncio.Event()
    release = asyncio.Event()

    async def upstream(payload, *args, **kwargs):
        nonlocal peak
        label = payload.instructions
        dispatched[label] += 1
        active.add(label)
        peak = max(peak, len(active))
        if len(active) >= 4:
            saturated.set()
        try:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "response.created",
                        "response": {"id": f"resp_{label}", "status": "in_progress", "output": []},
                    }
                )
                + "\n\n"
            )
            await release.wait()
            if label.endswith("failed"):
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "response.failed",
                            "response": {
                                "id": f"resp_{label}",
                                "status": "failed",
                                "output": [],
                                "error": {"code": "invalid_request_error", "message": "synthetic failure"},
                            },
                        }
                    )
                    + "\n\n"
                )
            else:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "response.completed",
                            "response": {
                                "id": f"resp_{label}",
                                "status": "completed",
                                "output": [],
                                "usage": {"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
                            },
                        }
                    )
                    + "\n\n"
                )
        finally:
            active.remove(label)

    monkeypatch.setattr(proxy_service, "core_stream_responses", upstream)

    async def call(label):
        return await async_client.post(
            "/v1/responses",
            headers={"x-request-id": f"req_{label}"},
            json={"model": "gpt-5.1", "instructions": label, "input": [], "stream": False},
        )

    tasks = [
        asyncio.create_task(call(f"mixed_{index}_{'failed' if index % 4 == 0 else 'slow'}")) for index in range(12)
    ]
    try:
        await asyncio.wait_for(saturated.wait(), 5)
        await asyncio.sleep(0.05)
        assert peak <= 8, dict(dispatched)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 15)
        assert all(result.status_code in {200, 400, 429, 502, 503} for result in results)
        assert any(result.status_code == 200 for result in results)
        assert all(count == 1 for count in dispatched.values()), "Visible upstream failures were replayed."
        assert not active
        healthy = await call("mixed_followup_success")
        assert healthy.status_code == 200
        assert dispatched["mixed_followup_success"] == 1
        await app_instance.state.proxy_service.drain_persistence_tasks(timeout_seconds=5)
        async with SessionLocal() as session:
            records = (
                (await session.execute(select(RequestLog).where(RequestLog.archive_request_id.like("req_mixed_%"))))
                .scalars()
                .all()
            )
        assert len(records) == 13
        assert len({record.archive_request_id for record in records}) == 13
        assert len(dispatched) == 13
        account_ids = {record.account_id for record in records if record.account_id is not None}
        assert len(account_ids) == 1
        for selected_account_id in account_ids:
            pressure = await app_instance.state.proxy_service._load_balancer.account_pressure_snapshot(
                selected_account_id
            )
            assert pressure[:2] == (0, 0)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
