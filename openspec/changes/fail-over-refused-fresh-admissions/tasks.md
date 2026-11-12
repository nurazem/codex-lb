## 1. Refused WebSocket upgrade

- [x] 1.1 Mark a non-fallback WebSocket handshake rejection as undispatched (`failure_phase = "handshake"`)
- [x] 1.2 Do not bind an account-bound body to the account that refused the upgrade
- [x] 1.3 Regression tests: marker, failover of an account-bound body, dispatched 403 stays bound

## 2. Overload refusal after the lifecycle prelude (HTTP stream)

- [x] 2.1 Hold `response.created` / `response.in_progress` for a movable, non-background attempt
- [x] 2.2 Raise a retryable admission refusal for an output-free `server_is_overloaded` / `overloaded_error` terminal; release the prelude for anything else
- [x] 2.3 Do not bind an account-bound body to the refusing account
- [x] 2.4 Regression tests: failover with and without a prelude, refusal after output, billed refusal, bare `server_error`, previous-response owner
