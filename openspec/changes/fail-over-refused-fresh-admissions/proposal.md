## Why

On 2026-11-12 five of eight accounts were weekly-quota exhausted and three
served all traffic. One (c0ba6dc7) was healthy; upstream refused two others
(a0a91a3b, 63a380d1) with `server_is_overloaded` on 30-50% of fresh turns.
About 4% of 30.5k requests in six hours failed, and almost none of the failures
were retried on another account:

1. **Isolated accounts kept receiving fresh work.** Overload isolation engaged
   repeatedly for both refusing accounts, yet 99% of their selections happened
   while they were isolated. Selection drops capped accounts before it applies
   overload preference, so whenever the healthy account sat at its per-account
   stream cap the remaining pool held only isolated accounts, and the
   "never empty the pool" rule selected them immediately instead of waiting a
   moment for the healthy account to free a slot.
2. **An admission refusal after the lifecycle prelude was relayed, not retried.**
   On the HTTP streaming path upstream sends `response.created` (and
   `response.in_progress`) and then `response.failed` with
   `server_is_overloaded` before producing any output. The prelude was forwarded
   at once, which made the turn downstream-visible, so the refusal could only be
   surfaced (Codex shows "Selected model is at capacity"). Of 735 refused
   requests only 5 were ever retried.
3. **A refused WebSocket upgrade bound the body to the refusing account.** A
   bare 403 on the upstream WebSocket upgrade ("Invalid response status") was
   treated as possibly dispatched, so every account-bound Codex body was pinned
   to the refusing account and the 403 was surfaced (152 surfaced vs 17 failed
   over in the incident window).

## What Changes

- A WebSocket upgrade that upstream refuses is marked undispatched, so a
  movable request fails over instead of being bound to the refusing account.
- On the HTTP streaming path, a fresh request that can still move holds back
  the output-free lifecycle prelude; an explicit overload refusal that arrives
  before any output is retried on another eligible account, and any other
  event releases the prelude unchanged.
- Fresh and soft-sticky selection waits briefly (bounded) for a slot on a
  healthy candidate that is only at its stream cap before it selects an
  overload-isolated account. Hard continuity owners are untouched.

## Impact

- `app/core/clients/proxy.py`, `app/modules/proxy/_service/streaming/`,
  `app/modules/proxy/_load_balancer/`, `app/modules/proxy/load_balancer.py`.
- No new settings. No migration.
