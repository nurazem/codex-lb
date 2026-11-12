## ADDED Requirements

### Requirement: Selection waits briefly for a capped healthy account before an isolated one

For fresh (unbound) and soft-sticky selection with a lease kind, when the per-account caps leave only overload-isolated accounts among the candidates selection could otherwise pick, and a candidate that is not in overload backoff and passes non-cap routing eligibility was dropped by the caps alone, the balancer MUST wait for an account lease to be released instead of selecting an isolated account at once, and then re-evaluate the pool. The wait MUST be bounded per selection call (10 seconds, a module constant) and MUST NOT hold the runtime lock. When no healthy slot frees in time the balancer MUST select from the isolated accounts exactly as before, so the overload window still never empties the pool. A soft-sticky owner served by the healthy account this way is a request-local release: its mapping is retained. Hard continuity owners (resolved hard `CODEX_SESSION` rows, previous-response, bridge and file owners) MUST NOT wait and MUST NOT be moved.

#### Scenario: A prompt-cache turn owned by an isolated account waits for the healthy account

- **GIVEN** a healthy account at its stream cap and two overload-isolated accounts, one of which owns the prompt-cache mapping
- **WHEN** a stream lease on the healthy account is released while the turn is being selected
- **THEN** the turn is served by the healthy account
- **AND** the prompt-cache mapping still names the isolated owner

#### Scenario: No slot frees in time

- **GIVEN** the same pool and no lease is released
- **WHEN** the bounded wait expires
- **THEN** an isolated account is selected

#### Scenario: A hard owner does not wait

- **GIVEN** a resolved hard `CODEX_SESSION` owner that is isolated and a healthy account at its cap
- **WHEN** the turn is selected
- **THEN** the hard owner is selected without waiting
