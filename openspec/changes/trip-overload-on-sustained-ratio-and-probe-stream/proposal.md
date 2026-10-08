## Why

On 2026-10-08 two Pro accounts were refused by upstream for about 45 minutes
while six siblings serving the same traffic stayed clean. Every refusal had the
same shape: HTTP 200, normal lifecycle frames, then `response.failed` with
`server_is_overloaded` or a bare `server_error`. The refused accounts ran at
15-16% overload-class failures per 10 minutes (25-31% of all requests in the
worst hour) and their *successful* turns took 4-7x longer than the siblings'.
They stayed in rotation the whole time. Failover fired 4 times against roughly
40 errors, and the operator's Force Probe would have reported both accounts as
healthy.

Two gaps explain it:

1. **The overload window only counts.** It trips on a weighted three rejections
   inside 120 seconds. At ~4 requests a minute, a 15% refusal rate is about one
   rejection per 120 s, so the window never filled. Only the error-rate weight
   (`max(0.05, 1 - error_rate)`, i.e. ~0.75) shaved the accounts' share, and
   established soft sticky owners kept landing on them.
2. **Force Probe reads only the HTTP status.** It never consumes the SSE body,
   so a 200 followed by an in-stream refusal probes as healthy and settles as a
   success into replica-local health.

## What Changes

- **Sustained-ratio trip.** Every overload-class observation (explicit and
  bare, unweighted) also enters a ratio window equal to the error-rate window
  (600 s). The overload window additionally trips when there are at least 5
  such observations, the account has at least 10 recorded outcomes in that
  window, and the observations are at least 10% of those outcomes. A ratio trip
  is an ordinary trip: same level, deadline, decay, isolation escalation and
  logging; it clears all three windows. New replica-local
  `RuntimeState.overload_rate_rejections`, copied in the opportunistic-admission
  snapshot like the other windows.
- **Force Probe reads the stream.** For a 2xx probe the service reads the SSE
  body to its terminal frame. `response.completed` and `response.incomplete`
  (the probe caps output at the token floor) count as served; `response.failed`
  and `error` report their code; a stream that ends without a terminal reports
  `stream_incomplete`; a read timeout reports `probe_stream_timeout` and keeps
  the HTTP status. The response gains optional `probe_stream_terminal` and
  `probe_stream_error_code`. Settlement treats a 2xx whose stream failed as a
  failed probe (it is settled with HTTP 502), so it resets the probe-success
  streak instead of advancing it. Non-2xx and network-failure behaviour is
  unchanged.

## Not changed (documented in context.md)

- **Transparent failover of in-stream refusals.** The proxy forwards
  `response.created` as soon as it arrives, and
  `_should_retry_transient_stream_error` deliberately refuses to replay a turn
  once upstream produced a response id. Moving an in-stream refusal to a
  sibling would require deferring the lifecycle preamble and revisiting that
  replay rule; out of scope here.
- `stream_incomplete` does not feed the overload windows: during the incident it
  appeared on healthy accounts at the same rate as on the refused ones.

## Impact

- Specs: `account-routing` (ADDED: sustained-ratio trip),
  `usage-refresh-policy` (ADDED: Force Probe reads the stream).
- Code: `_load_balancer/overload_backoff.py`, `_load_balancer/types.py`,
  `_load_balancer/opportunistic_admission.py`, `modules/accounts/service.py`,
  `modules/accounts/schemas.py`, `modules/accounts/api.py`.
- Tests: `tests/unit/test_overload_backoff.py` (7 added),
  `tests/unit/test_accounts_service_probe.py` (8 added, transport test updated),
  `tests/integration/test_accounts_api_probe.py` (1 added); probe fakes return
  `ProbeOutcome`.
- Replica-local state only: no migration, no new setting, no new metric. The
  probe response adds two optional fields; the dashboard schema ignores unknown
  keys.
