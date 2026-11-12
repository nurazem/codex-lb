## ADDED Requirements

### Requirement: A refused WebSocket upgrade does not bind the request body

When upstream answers the WebSocket upgrade for a Responses stream with a non-101 status and the proxy does not fall back to HTTP, the resulting error MUST be marked as an undispatched upstream rejection (`failure_phase = "handshake"`, with the upstream status recorded). The streaming retry loop MUST NOT record the refusing account as the dispatch owner of an account-bound body for such an error, so a request that is otherwise movable fails over under the normal failover decision. The marker MUST NOT grant same-account replay or the dead-route backoff reserved for confirmed pre-dispatch transport failures, and an error from a dispatched HTTP request MUST keep its existing owner binding.

#### Scenario: Account-bound body fails over after a refused upgrade

- **GIVEN** two selectable accounts and a fresh streaming request whose input carries encrypted reasoning
- **WHEN** the first account's WebSocket upgrade is refused with HTTP 403
- **THEN** the request is sent to the second account
- **AND** the 403 is not surfaced to the client

#### Scenario: A dispatched HTTP rejection keeps the body on its owner

- **GIVEN** the same request
- **WHEN** the first account rejects the dispatched HTTP request with 403
- **THEN** the body is not sent to another account and the failure is surfaced
