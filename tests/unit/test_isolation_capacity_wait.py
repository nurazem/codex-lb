"""Overload-isolated accounts are not selected while a healthy one is only capped.

Production evidence (2026-11-12): two accounts upstream refused on 30-50% of
fresh turns were overload-isolated, yet 99% of their selections happened while
isolated. The only healthy account sat at its per-account stream cap, the cap
filter dropped it before overload preference ran, and the "never empty the
pool" rule then handed every fresh and prompt-cache turn to an isolated account.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest

from app.db.models import StickySessionKind
from app.modules.proxy._load_balancer import sticky_selection as sticky_selection_module
from app.modules.proxy._load_balancer.overload_backoff import OVERLOAD_ISOLATION_TRIP_LEVEL
from app.modules.proxy._load_balancer.types import RuntimeState
from app.modules.proxy.load_balancer import LoadBalancer
from tests.unit.test_load_balancer_concurrency import (
    _make_account,
    _repo_factory,
    _StubAccountsRepository,
    _StubStickySessionsRepository,
    _StubUsageRepository,
    _usage_row,
)

pytestmark = pytest.mark.unit

_STREAM_CAP = 8


def _pool(prefix: str):
    now_epoch = int(datetime.now(tz=timezone.utc).timestamp())
    healthy = _make_account(f"{prefix}-healthy")
    isolated_owner = _make_account(f"{prefix}-isolated-owner")
    isolated_other = _make_account(f"{prefix}-isolated-other")
    accounts = [healthy, isolated_owner, isolated_other]
    primary = {
        account.id: _usage_row(index + 100, account.id, window="primary", reset_at=now_epoch + 300)
        for index, account in enumerate(accounts)
    }
    secondary = {
        account.id: _usage_row(index + 200, account.id, window="secondary", reset_at=now_epoch + 3600)
        for index, account in enumerate(accounts)
    }
    sticky_repo = _StubStickySessionsRepository()
    balancer = LoadBalancer(
        lambda: _repo_factory(_StubAccountsRepository(accounts), _StubUsageRepository(primary, secondary), sticky_repo)
    )
    now = balancer._clock.time()
    for account in (isolated_owner, isolated_other):
        balancer._runtime[account.id] = RuntimeState(
            overload_backoff_until=now + 1800.0,
            overload_isolated_until=now + 1800.0,
            overload_backoff_level=OVERLOAD_ISOLATION_TRIP_LEVEL,
            overload_last_trip_at=now,
        )
    return balancer, healthy, isolated_owner, isolated_other, sticky_repo


async def _saturate(balancer: LoadBalancer, account_id: str):
    leases = [await balancer.acquire_account_lease(account_id, kind="stream") for _ in range(_STREAM_CAP)]
    assert all(lease is not None for lease in leases)
    return leases


async def _release_soon(balancer: LoadBalancer, lease, delay: float = 0.05) -> None:
    await asyncio.sleep(delay)
    await balancer.release_account_lease(lease)


@pytest.mark.asyncio
async def test_prompt_cache_turn_waits_for_the_capped_healthy_account(monkeypatch):
    monkeypatch.setattr(sticky_selection_module, "ISOLATION_CAPACITY_WAIT_SECONDS", 5.0, raising=False)
    balancer, healthy, isolated_owner, _, sticky_repo = _pool("pc-wait")
    sticky_repo.account_ids_by_key = {"prompt-cache-key": isolated_owner.id}
    leases = await _saturate(balancer, healthy.id)

    releaser = asyncio.create_task(_release_soon(balancer, leases[0]))
    selected = await balancer.select_account(
        sticky_key="prompt-cache-key",
        sticky_kind=StickySessionKind.PROMPT_CACHE,
        routing_strategy="capacity_weighted",
        lease_kind="stream",
    )
    await releaser

    assert selected.account is not None, selected.error_message
    assert selected.account.id == healthy.id
    # Request-local release: the thread returns to its owner once isolation lifts.
    assert sticky_repo.upserts == []
    assert sticky_repo.deleted == []
    for lease in [*leases[1:], selected.lease]:
        await balancer.release_account_lease(lease)


@pytest.mark.asyncio
async def test_fresh_turn_waits_for_the_capped_healthy_account(monkeypatch):
    monkeypatch.setattr(sticky_selection_module, "ISOLATION_CAPACITY_WAIT_SECONDS", 5.0, raising=False)
    balancer, healthy, _, _, _ = _pool("fresh-wait")
    leases = await _saturate(balancer, healthy.id)

    releaser = asyncio.create_task(_release_soon(balancer, leases[0]))
    selected = await balancer.select_account(routing_strategy="capacity_weighted", lease_kind="stream")
    await releaser

    assert selected.account is not None, selected.error_message
    assert selected.account.id == healthy.id
    for lease in [*leases[1:], selected.lease]:
        await balancer.release_account_lease(lease)


@pytest.mark.asyncio
@pytest.mark.parametrize("sticky", [False, True])
async def test_isolated_account_is_selected_when_no_healthy_slot_frees_in_time(monkeypatch, sticky):
    # The wait is bounded and the pool is never emptied.
    monkeypatch.setattr(sticky_selection_module, "ISOLATION_CAPACITY_WAIT_SECONDS", 0.1, raising=False)
    balancer, healthy, isolated_owner, isolated_other, sticky_repo = _pool(f"timeout-{sticky}")
    sticky_repo.account_ids_by_key = {"prompt-cache-key": isolated_owner.id}
    leases = await _saturate(balancer, healthy.id)
    kwargs = {"sticky_key": "prompt-cache-key", "sticky_kind": StickySessionKind.PROMPT_CACHE} if sticky else {}

    started = time.monotonic()
    selected = await balancer.select_account(routing_strategy="capacity_weighted", lease_kind="stream", **kwargs)
    elapsed = time.monotonic() - started

    assert selected.account is not None, selected.error_message
    assert selected.account.id in {isolated_owner.id, isolated_other.id}
    assert elapsed >= 0.1
    assert elapsed < 2.0
    for lease in [*leases, selected.lease]:
        await balancer.release_account_lease(lease)


@pytest.mark.asyncio
async def test_hard_continuity_owner_is_selected_without_waiting(monkeypatch):
    monkeypatch.setattr(sticky_selection_module, "ISOLATION_CAPACITY_WAIT_SECONDS", 5.0, raising=False)
    balancer, healthy, isolated_owner, _, sticky_repo = _pool("hard-owner")
    sticky_repo.account_ids_by_key = {"codex-session-key": isolated_owner.id}
    leases = await _saturate(balancer, healthy.id)

    started = time.monotonic()
    selected = await balancer.select_account(
        sticky_key="codex-session-key",
        sticky_kind=StickySessionKind.CODEX_SESSION,
        routing_strategy="capacity_weighted",
        lease_kind="stream",
    )

    assert selected.account is not None, selected.error_message
    assert selected.account.id == isolated_owner.id
    assert time.monotonic() - started < 1.0
    for lease in [*leases, selected.lease]:
        await balancer.release_account_lease(lease)


@pytest.mark.asyncio
async def test_no_wait_when_the_healthy_account_has_capacity(monkeypatch):
    monkeypatch.setattr(sticky_selection_module, "ISOLATION_CAPACITY_WAIT_SECONDS", 5.0, raising=False)
    balancer, healthy, isolated_owner, _, sticky_repo = _pool("has-capacity")
    sticky_repo.account_ids_by_key = {"prompt-cache-key": isolated_owner.id}

    started = time.monotonic()
    selected = await balancer.select_account(
        sticky_key="prompt-cache-key",
        sticky_kind=StickySessionKind.PROMPT_CACHE,
        routing_strategy="capacity_weighted",
        lease_kind="stream",
    )

    assert selected.account is not None, selected.error_message
    assert selected.account.id == healthy.id
    assert time.monotonic() - started < 1.0
    await balancer.release_account_lease(selected.lease)
