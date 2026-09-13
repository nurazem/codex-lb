# Settle non-streaming Responses on client disconnect

## Why

The non-streaming Responses route buffers a service stream before returning a response. Unlike a streaming response body, this collection does not automatically observe ASGI disconnect. A departed client can leave local collection and upstream request ownership active until a later upstream terminal event.

## What changes

Observe client disconnect while collecting a final response, cancel the owned collection once, and join its existing service cleanup. Preserve completed results and established reservation ownership. Add native ASGI disconnect and concurrent lifecycle controls.

## Impact

Responses API compatibility collection; no database, credential, model, timeout or routing policy changes. Remote cancellation is not inferred from local closure.
