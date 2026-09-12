## Why

Non-streaming Responses aggregation currently keys item snapshots by output index. When an item's index changes and another item reuses it, a completed payload can be overwritten by an added snapshot or another item, silently losing encrypted content or tool arguments.

## What Changes

- Reconstruct absent terminal output from completed items keyed by stable item ID.
- Preserve first-observed index ordering, with completed snapshots taking precedence over added snapshots.
- Fail with an OpenAI-style upstream contract error when reconstruction is incomplete or ambiguous.
- Retain authoritative non-empty terminal output and the existing stream-draining lifecycle.

## Impact

- Affects non-streaming Responses collection only; no settings or deployment changes.
- Adds route regressions and updates the Responses compatibility specification.
