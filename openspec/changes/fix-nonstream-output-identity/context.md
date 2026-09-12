# Completed output identity

The non-streaming collector must not use mutable output indexes as item identity. For example, A added at index 8 and completed at index 9 followed by B at index 9 must retain both completed payloads. Index-keyed aggregation instead retains the early A snapshot and overwrites completed A with B.

The collector tracks the first observed index per item ID for ordering and retains only done snapshots for terminal reconstruction. Equal first indexes across identities cannot establish an unambiguous order and fail closed. Identical repeated done snapshots are harmless; conflicting ones fail closed. Opaque fields, including encrypted content and tool arguments, are retained without reconstructing them from deltas.

Non-empty terminal output remains authoritative. Existing public normalization still applies. Queued and in-progress acknowledgements do not require completed items. Errors and failed responses retain their existing handling, and the iterator is drained after the first terminal result so upstream finalization still runs.

This change only alters final JSON collection. Streaming normalization keeps its existing contract. No new configuration or deployment step is required.
