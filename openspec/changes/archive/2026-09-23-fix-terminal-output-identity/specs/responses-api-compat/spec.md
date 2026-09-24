## ADDED Requirements

### Requirement: Identity-safe terminal backfill
The public Responses normalizer SHALL associate a completed output item with its unique registered identity and type when its reported completion index is unoccupied. It SHALL retain registration order and emit each identity once when backfilling an empty terminal output. It SHALL NOT rewrite lifecycle events or replace nonempty upstream terminal output.

#### Scenario: Shifted completion
- **WHEN** an item completes at an unoccupied index different from its unique registration
- **THEN** the terminal backfill contains the completed item at its registered position, without a stale duplicate

#### Scenario: Conflicting lifecycle evidence
- **WHEN** identity is ambiguous, the shifted target belongs to another item, item type changes, or a repeated completion conflicts
- **THEN** the public stream terminates with a protocol error instead of fabricating a successful terminal snapshot
