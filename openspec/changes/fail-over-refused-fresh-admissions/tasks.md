## 1. Refused WebSocket upgrade

- [x] 1.1 Mark a non-fallback WebSocket handshake rejection as undispatched (`failure_phase = "handshake"`)
- [x] 1.2 Do not bind an account-bound body to the account that refused the upgrade
- [x] 1.3 Regression tests: marker, failover of an account-bound body, dispatched 403 stays bound

## 2. Overload refusal after the lifecycle prelude (HTTP stream)

- [x] 2.1 Hold `response.created` / `response.in_progress` for a movable, non-background attempt
- [x] 2.2 Raise a retryable admission refusal for an output-free `server_is_overloaded` / `overloaded_error` terminal; release the prelude for anything else
- [x] 2.3 Do not bind an account-bound body to the refusing account
- [x] 2.4 Regression tests: failover with and without a prelude, refusal after output, billed refusal, bare `server_error`, previous-response owner, refusal on every account, refusal after the hold expired
- [x] 2.5 Hold above the attempt (in the retry loop), not in the streaming mixin: keeps the mixin at its line ratchet and releases the response-create slot on the first upstream frame; bound the hold at 15 s

## 3. Isolated accounts while a healthy account is only capped

- [x] 3.1 Signal account lease releases from the balancer
- [x] 3.2 Fresh and soft-sticky selection waits (bounded, outside the runtime lock) for a capped healthy candidate before selecting an isolated account; hard owners never wait
- [x] 3.3 Regression tests: prompt-cache and fresh turns wait and land on the healthy account, bounded fallback to isolated accounts, hard owner without wait, no wait when the healthy account has capacity

## 4. Verification

- [x] 4.1 Focused unit and integration tests green
- [ ] 4.2 Deploy and confirm isolated accounts stop receiving fresh selections while a healthy account has capacity, and refused admissions show a second selection
