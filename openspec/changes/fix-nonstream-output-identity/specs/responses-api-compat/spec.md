## ADDED Requirements

### Requirement: Non-streaming output reconstruction preserves completed item identity

When collecting a non-streaming Responses result whose terminal output is absent, null, or empty, the service MUST reconstruct output from `response.output_item.done` snapshots keyed by non-empty item ID. It MUST include each identity exactly once and preserve its completed payload through existing public output normalization, even when an item's output index changes or a later item reuses that index. Ordering MUST follow each identity's first observed output index. Added snapshots MUST NOT replace completed snapshots.

If reconstruction encounters invalid item identity or index, conflicting completed snapshots for one ID, conflicting item types, repeated function-call IDs across different items, equal first-observed indexes across different identities, an item that public normalization cannot represent, or an item without a done snapshot, the service MUST return an `invalid_output_item` upstream error rather than a partial successful result. A non-empty terminal output MUST remain authoritative and use existing public response validation. Collection MUST retain first-terminal-result semantics and drain the upstream iterator to completion.

#### Scenario: Item index shifts and is reused

- **GIVEN** item A is added at index 8 and completed at index 9, then item B is added and completed at index 9
- **WHEN** a completed response has null output
- **THEN** the final JSON output contains completed A and completed B exactly once in that order, retaining both encrypted payloads

#### Scenario: Reconstruction is ambiguous

- **GIVEN** two different completed snapshots share an item ID, or an added item never completes
- **WHEN** a completed response has empty output
- **THEN** the service returns an upstream `invalid_output_item` error instead of successful partial output

#### Scenario: Authoritative terminal output

- **GIVEN** streamed item snapshots are incomplete or have conflicting indexes
- **WHEN** the terminal response contains non-empty valid output
- **THEN** the service uses that terminal output without merging earlier snapshots
