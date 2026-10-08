## Incident evidence (2026-10-08, one deployment, gpt-6.1-sol)

- Two Pro accounts, quota barely used (5% and 11% of the primary window), began
  failing within the same few minutes (01:49-01:55 UTC). Six siblings under the
  same traffic stayed below 1% overload-class failures.
- Failures were HTTP 200 + `response.failed` (`server_is_overloaded`, bare
  `server_error`), arriving 0.7-56 s into the stream. No upstream HTTP status.
- 01:45-02:31 UTC: 200 and 199 requests, 35 and 31 errors on the two accounts.
  Successful turns averaged 26-31 s vs 7-8 s on siblings.
- A controlled probe at 02:58 UTC with identical requests through the same edge:
  refused accounts completed 5/8 and 3/8 small requests (all failures
  `server_is_overloaded`), successes 11-14 s; siblings 8/8 at ~2 s.
- No `Account overload backoff engaged` lines in that window; failover decisions
  4 in four hours.

## Why a ratio and not a lower count

A lower count threshold or a longer count window would trip busy healthy
accounts on scattered hiccups. Tying the trip to the account's own outcome
volume keeps the evidence proportional: 5 refusals out of 200 outcomes is noise,
5 out of 37 is a refusing account. The ratio window reuses the error-rate
window and its 10-outcome evidence floor so the two signals agree on what
"recent" means.

## Transparent failover (not implemented)

`settlement.downstream_visible` is set when the first upstream frame is
forwarded (`_service/streaming/mixin.py`), normally `response.created`, which
also publishes response ownership. `_should_retry_transient_stream_error`
returns False once a response id exists, by design: the dispatched turn may
have side effects upstream. Even a first-frame `response.failed` carries a
response id. Implementing pre-visible failover for these refusals would mean
buffering the lifecycle preamble until the first content frame and deciding
that replaying a refused, store=false turn is safe. That is a separate change
with its own risk to TTFT, ownership publication and bridge continuity.

## Example

Account at 4 requests/minute over 500 s (33 successes) with refusals at
t=0, 100, 200, 300, 400 s: the count window never holds more than two soft
observations (weight 1.0 < 3). At t=400 s the ratio window holds 5 refusals
against 37 outcomes (13.5%), so the window trips at level 1 (60 s backoff).
Sustained refusal trips again after each backoff and reaches isolation at the
third trip, where soft sticky owners are served by a sibling.
