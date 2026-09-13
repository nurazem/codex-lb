## ADDED Requirements

### Requirement: Non-streaming collection owns disconnect settlement

While collecting a synchronous non-streaming Responses result, the proxy MUST observe downstream ASGI disconnect. A disconnect before collection finishes MUST cancel the owned collection once and await its existing cleanup. The observer MUST NOT independently release a reservation owned by the service, trigger failover, or infer remote settlement. A completed collection MUST preserve its result and terminal usage settlement when completion and disconnect become observable together. Request teardown MUST leave no unowned disconnect watcher or collection task.

#### Scenario: Client disconnects before the upstream terminal

- **GIVEN** a non-streaming request has entered its service-owned upstream operation
- **WHEN** the downstream client disconnects before a terminal response is collected
- **THEN** the proxy cancels and awaits collection and local stream cleanup
- **AND** the existing owner settles the API-key reservation exactly once without a replacement upstream attempt

#### Scenario: Completion and disconnect are both observable

- **GIVEN** collection has completed with an authoritative terminal result
- **WHEN** downstream disconnect is also observed
- **THEN** the completed result and its established settlement remain authoritative
- **AND** no second cleanup owner or retry is created

#### Scenario: Other requests remain active

- **GIVEN** multiple independent non-streaming requests are in flight
- **WHEN** one client disconnects
- **THEN** its owned work settles without cancelling another request or releasing another request's reservation
