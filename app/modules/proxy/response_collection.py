"""Own final-response collection until completion or downstream disconnect."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from starlette.requests import Request

from app.core.clock import REAL_SCHEDULER, Scheduler
from app.core.utils.shared_future import _await_cleanup_deferring_cancellation

_T = TypeVar("_T")


async def collect_until_disconnect(
    request: Request, operation: Coroutine[Any, Any, _T], *, scheduler: Scheduler = REAL_SCHEDULER
) -> _T:
    """Cancel collection once on disconnect and join its existing cleanup owner."""

    async def disconnected() -> None:
        while True:
            message = await request.receive()
            if message["type"] == "http.disconnect":
                return
            await scheduler.sleep(0)

    collection = scheduler.create_task(operation, name="nonstream-response-collection")
    watcher = scheduler.create_task(disconnected(), name="nonstream-disconnect-watcher")
    try:
        await scheduler.wait((collection, watcher), return_when=asyncio.FIRST_COMPLETED)
        # A collected terminal owns its result/settlement even if disconnect is
        # observable in the same loop turn. Do not convert success into failure.
        if collection.done():
            return collection.result()
        watcher.result()
        raise asyncio.CancelledError("Downstream client disconnected during response collection")
    finally:
        for task in (collection, watcher):
            if not task.done():
                task.cancel()
        joined = asyncio.gather(collection, watcher, return_exceptions=True)
        # Preserve the existing cleanup owner through edge and ASGI level
        # cancellation without repeated shield callbacks or a busy loop.
        interrupted = await _await_cleanup_deferring_cancellation(joined, scheduler=scheduler)
        if interrupted is not None:
            raise interrupted
