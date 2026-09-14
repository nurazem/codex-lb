# Record HTTP upstream progress

## Why

An archived outbound request followed by no archived response does not distinguish waiting for headers, receiving incomplete SSE bytes, waiting between events, or incomplete archive capture. Operators need payload-free progress evidence independent of payload archive retention.

## What Changes

- Add bounded, zero-configuration HTTP upstream attempt diagnostics for admission, response headers, first body bytes, first parsed event, and exit.
- Retain elapsed timings and byte/event counts in the exit summary, including cancellation and iterator closure.
- Explicitly label archive capture completeness as unverified; archive enablement or successful enqueue is not durable completeness.
- Preserve request timeouts, routing, retries, settlement, and payload delivery.
- Use the existing cancellation-deferring cleanup helper for the deployed non-streaming collector; its repeated `asyncio.shield` loop fails the repository cancellation-safety gate and can spin under ASGI level cancellation.

## Impact

- Affects `proxy-runtime-observability` and the HTTP Responses upstream client.
- No settings, database schema, or dashboard changes.
