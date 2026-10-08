## ADDED Requirements

### Requirement: Canonical public streamed item indexes
The public Responses stream SHALL use the uniquely registered output index for later item-scoped events with a matching stable item ID when the reported target index is unoccupied. It SHALL reject conflicting registrations, types, occupied targets and completed contents rather than infer ownership. It SHALL preserve native passthrough and leave nonempty terminal output authoritative.

#### Scenario: Hosted-search completion index drift
- **WHEN** a search registers at N and completes at unoccupied N+1 with the same ID
- **THEN** its public lifecycle and item completion carry N and its terminal backfill contains one completed item

#### Scenario: Native stream
- **WHEN** SDK contract enforcement is disabled
- **THEN** upstream item indexes remain unchanged

## MODIFIED Requirements

### Requirement: Identity-safe terminal backfill
The public Responses normalizer SHALL associate a completed output item with its unique registered identity and type when its reported completion index is unoccupied. It SHALL retain registration order and emit each identity once when backfilling an empty terminal output. It SHALL preserve nonempty upstream terminal output. Public item-scoped lifecycle events SHALL carry the unique registered index when the reported target is unoccupied; native passthrough SHALL retain upstream indexes.

#### Scenario: Shifted completion
- **WHEN** an item completes at an unoccupied index different from its unique registration
- **THEN** the terminal backfill contains the completed item at its registered position, without a stale duplicate

#### Scenario: Conflicting lifecycle evidence
- **WHEN** identity is ambiguous, the shifted target belongs to another item, item type changes, or a repeated completion conflicts
- **THEN** the public stream terminates with a protocol error instead of fabricating a successful terminal snapshot


