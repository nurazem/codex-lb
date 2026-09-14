# HTTP attempt progress diagnostics

HTTP responses previously lacked enough progress evidence to distinguish waiting for
headers, receiving unparsed bytes, and receiving normalized events. A final timeout
or cancellation alone cannot identify which boundary stopped making progress.

Each HTTP attempt now emits at most five `http_upstream_progress` records: `start`,
`headers`, `first_byte` (SSE only), `first_event`, and `exit`. Join by `attempt_id`
within the ingress `request_id`; retries have separate attempt IDs. Times are
monotonic milliseconds from attempt start. The exit record retains the last byte
and event times and their cumulative counts without logging every chunk.

For example, this synthetic exit record shows bytes received without a normalized
event before cancellation:

```json
{"schema_version":1,"request_id":"synthetic-request","attempt_id":"synthetic-attempt","phase":"exit","elapsed_ms":2000,"body_format":"sse","status_code":200,"headers_ms":30,"first_byte_ms":40,"first_event_ms":null,"last_byte_ms":1900,"last_event_ms":null,"received_bytes":120,"received_events":0,"terminal_observed":false,"exit_kind":"cancelled","archive_enabled":false,"archive_capture_complete":null}
```

A missing `headers_ms` means this attempt did not observe response headers. Nonzero
bytes with zero events means bytes reached the parser without producing a complete
normalized event. A missing terminal means no terminal was observed by this layer;
it does not prove the upstream failed to generate one. `exit_kind` describes the
local iterator exit (`returned`, `timeout`, `cancelled`, `closed`, or `error`).
JSON responses retain header and normalized-event evidence but leave raw byte
counts and byte timestamps unset because that path uses the JSON response reader.

Payload archive retention is independent. `archive_enabled` reports configuration;
`archive_capture_complete` remains null because this channel has no archive flush
receipt. Progress logs are not complete wire captures. No payload, URL, headers,
account identifier, or exception message is included in these records.

Loopback HTTP tests cover terminal SSE, JSON, cancellation before headers, partial
SSE cancellation and timeout, and explicit consumer close. Cancellation cleanup
also runs inside a level-cancelled ASGI scope to verify that the collector can
finish without spinning or leaking shield callbacks.

The required container scan also found fixed critical issues in the inherited
Perl package. The runtime image's existing security-upgrade list now includes
`perl-base`; rebuilding and scanning the image verifies the package update.
