## ADDED Requirements

### Requirement: Full diagnostic stream boundaries
When conversation archiving is enabled, the proxy SHALL retain complete client request and response chunks, public normalizer input and output events, and upstream HTTP SSE and WebSocket messages before normalization. Existing archive authentication-header redaction and restricted-file permissions SHALL apply. Capture SHALL NOT alter forwarded bytes or protocol acceptance. End records SHALL distinguish normal completion from interruption and retain observed event counts; they SHALL NOT claim writer success or complete capture solely from enablement.

#### Scenario: Upstream item index changes
- **WHEN** one item changes output index during a captured request
- **THEN** the pre-normalization and post-normalization records retain the event payloads and correlation needed to identify the first changed boundary

#### Scenario: Capture is disabled
- **WHEN** conversation archiving is disabled
- **THEN** the added capture boundaries produce no archive records and forward the original request and response unchanged

### Requirement: Fork upgrade preserves both published database histories
The fork SHALL join the upstream SCIM and withdrawn-overflow migration heads with a no-op merge revision. Existing published revision identities SHALL remain unchanged.

#### Scenario: Upgrade the deployed database
- **WHEN** a copy of the deployed database upgrades to the fork head
- **THEN** the upgrade reaches one merged head and preserves existing account and request-log rows
