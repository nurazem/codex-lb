"""Own final-response collection until completion or downstream disconnect."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from starlette.requests import Request

_T = TypeVar("_T")


async def collect_until_disconnect(request: Request, operation: Awaitable[_T]) -> _T:
    """Cancel collection once on disconnect and join its existing cleanup owner."""

    async def disconnected() -> None:
        while True:
            message = await request.receive()
            if message["type"] == "http.disconnect":
                return
            await asyncio.sleep(0)

    collection = asyncio.ensure_future(operation)
    watcher = asyncio.create_task(disconnected())
    try:
        await asyncio.wait((collection, watcher), return_when=asyncio.FIRST_COMPLETED)
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
        interrupted: asyncio.CancelledError | None = None
        while not joined.done():
            try:
                await asyncio.shield(joined)
            except asyncio.CancelledError as exc:
                # The service already owns bounded persistence/stream cleanup.
                # Repeated caller cancellation must not cancel that owner again.
                interrupted = exc
        if interrupted is not None:
            raise interrupted
