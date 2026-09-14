## ADDED Requirements

### Requirement: HTTP upstream progress is independently observable
Each HTTP Responses upstream attempt MUST emit bounded structural console diagnostics for attempt start, received headers, first nonempty SSE body chunk, first parsed upstream event, and attempt exit when those boundaries are observed. The exit summary MUST retain elapsed timing, SSE byte and event counts, terminal-event observation, and whether the iterator exited normally, raised, was cancelled, or was closed. JSON response bodies MUST identify their body-byte observation as unavailable rather than inventing a wire byte count. Diagnostics MUST correlate by request and attempt identity without including payloads, credentials, URLs, account emails, exception messages, or raw upstream event names. They MUST NOT change retries, deadlines, or external settlement. Archive capture completeness MUST be explicitly unverified; archive enablement alone MUST NOT establish completeness.

#### Scenario: partial SSE bytes precede interruption
- **WHEN** an upstream sends nonempty bytes without a complete SSE event and the attempt is interrupted
- **THEN** the exit summary reports positive received bytes and zero parsed events
- **AND** preserves the interruption kind without recording the byte contents

#### Scenario: no response headers arrive
- **WHEN** an HTTP attempt exits before receiving headers
- **THEN** its summary retains missing header and first-event timings and the exit kind
- **AND** does not infer that the upstream provider accepted or settled the operation

#### Scenario: terminal upstream event is observed
- **WHEN** an HTTP SSE or JSON response supplies a recognized terminal response event
- **THEN** the summary records terminal observation independently of iterator closure
- **AND** archive capture completeness remains unverified
