## ADDED Requirements

### Requirement: Force Probe reads the stream to its terminal frame

When the Force Probe `responses.create` returns an HTTP 2xx status, the service MUST read the SSE body until a terminal frame or the end of the body, within the probe's existing request timeout. `response.completed` and `response.incomplete` MUST count as a served turn. `response.failed` and `error` frames MUST be reported as a stream failure carrying the frame's error code (or `upstream_error` when the frame has none). A body that ends without a terminal frame MUST be reported as `stream_incomplete`, and a read timeout after the status was received MUST be reported as `probe_stream_timeout` while keeping the received HTTP status. The probe response MUST carry `probe_stream_terminal` and `probe_stream_error_code` in addition to `probe_status_code`; both MUST be null for a non-2xx probe or the network-failure sentinel, whose bodies MUST NOT be read. Settlement into replica-local health MUST treat a 2xx probe whose stream failed as a failed observation, settled with HTTP 502, so it resets an in-progress probe-success streak and never counts as a success. The access token MUST NOT appear in logs or in the response.

#### Scenario: In-stream refusal after HTTP 200 is a failed probe

- **GIVEN** upstream answers the probe with HTTP 200, `response.created`, `response.in_progress` and then `response.failed` with code `server_is_overloaded`
- **WHEN** an operator runs Force Probe on the account
- **THEN** the response carries `probe_status_code=200`, `probe_stream_terminal="response.failed"` and `probe_stream_error_code="server_is_overloaded"`
- **AND** settlement records a failed observation rather than a success

#### Scenario: An incomplete turn at the output floor is served

- **GIVEN** upstream ends the probe turn with `response.incomplete` because of `max_output_tokens`
- **WHEN** the probe settles
- **THEN** it counts as a successful observation and `probe_stream_error_code` is null

#### Scenario: A stream that stops without a terminal frame is a failed probe

- **GIVEN** upstream answers HTTP 200 and the body ends after `response.created`
- **WHEN** the probe settles
- **THEN** `probe_stream_error_code` is `stream_incomplete` and settlement records a failed observation
