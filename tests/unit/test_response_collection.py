"""Final-response collection owns cancellation and joins cleanup."""

import asyncio

import anyio
import pytest
from starlette.requests import Request

from app.modules.proxy.response_collection import collect_until_disconnect

pytestmark = pytest.mark.unit


def request_for(disconnected):
    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    return Request({"type": "http"}, receive)


@pytest.mark.asyncio
async def test_completed_result_wins_simultaneous_disconnect():
    disconnected = asyncio.Event()
    disconnected.set()

    async def operation():
        return {"status": "completed"}

    assert await collect_until_disconnect(request_for(disconnected), operation()) == {"status": "completed"}


@pytest.mark.asyncio
async def test_collection_failure_preserves_original_exception():
    failure = ValueError("invalid upstream terminal")

    async def operation():
        raise failure

    with pytest.raises(ValueError) as caught:
        await collect_until_disconnect(request_for(asyncio.Event()), operation())
    assert caught.value is failure


@pytest.mark.asyncio
async def test_repeated_caller_cancel_does_not_interrupt_cleanup():
    started = asyncio.Event()
    closing = asyncio.Event()
    allow_close = asyncio.Event()
    closed = asyncio.Event()
    cancellations = []

    async def operation():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellations.append(True)
            raise
        finally:
            closing.set()
            await allow_close.wait()
            closed.set()

    owner = asyncio.create_task(collect_until_disconnect(request_for(asyncio.Event()), operation()))
    await started.wait()
    owner.cancel()
    await closing.wait()
    owner.cancel()
    await asyncio.sleep(0)
    assert not owner.done()
    allow_close.set()
    with pytest.raises(asyncio.CancelledError):
        await owner
    assert closed.is_set()
    assert cancellations == [True]


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_level_cancelled_asgi_scope_allows_cleanup_to_finish() -> None:
    started = asyncio.Event()
    closing = asyncio.Event()
    release = asyncio.Event()
    closed = asyncio.Event()
    scopes: list[anyio.CancelScope] = []

    async def operation() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closing.set()
            await release.wait()
            closed.set()

    async def owner() -> None:
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            await collect_until_disconnect(request_for(asyncio.Event()), operation())

    task = asyncio.create_task(owner())
    await started.wait()
    scopes[0].cancel()
    await closing.wait()
    # This task can run while the collector's outer scope stays cancelled.
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    await task
    assert closed.is_set()


@pytest.mark.asyncio
async def test_concurrent_success_failure_and_disconnect_have_independent_owners():
    gate = asyncio.Semaphore(2)
    active = 0
    peak = 0
    dispatches = []
    closed = []

    async def operation(index):
        nonlocal active, peak
        async with gate:
            dispatches.append(index)
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.01)
                if index % 3 == 1:
                    raise ValueError("upstream failure")
                return index
            finally:
                active -= 1
                closed.append(index)

    disconnects = [asyncio.Event() for _ in range(12)]
    owners = [
        asyncio.create_task(collect_until_disconnect(request_for(disconnects[i]), operation(i))) for i in range(12)
    ]
    await asyncio.sleep(0)
    for i in range(2, 12, 3):
        disconnects[i].set()
    results = await asyncio.gather(*owners, return_exceptions=True)
    assert active == 0 and peak <= 2
    assert sorted(dispatches) == sorted(closed)
    assert len(dispatches) == len(set(dispatches))
    for i, result in enumerate(results):
        if i % 3 == 0:
            assert result == i
        elif i % 3 == 1:
            assert isinstance(result, ValueError)
        else:
            assert isinstance(result, asyncio.CancelledError)
