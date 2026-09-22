# Retain full provider wire capture in the deployment fork

## Why
The production incident archive was disabled, and its existing HTTP response capture follows normalization. Temporary mounts are not durable source history. Merge upstream main while preserving deployed fork contracts, and make complete diagnostic boundaries part of the fork.

## What Changes
- Reuse the existing archive switch, restricted writer and header redaction.
- Capture client request/response chunks, normalizer input/output, and upstream HTTP SSE/WebSocket input before normalization.
- Preserve end records and counts without asserting archive completeness when writes fail.
- Do not change parser acceptance, routing, retries, or model behavior.

## Impact
Full workload bodies are sensitive. Existing archive access and retention apply; authentication headers remain redacted. No new setting or schema.

## Upstream integration prerequisite
Upstream main contains two published migration heads at the same timestamp. A no-op merge revision joins them without rewriting history. The existing timestamp-collision lint remains an upstream inherited warning/error; actual migrations must upgrade to the single merged head on a copied production database before deployment.
