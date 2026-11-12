## 1. Refused WebSocket upgrade

- [x] 1.1 Mark a non-fallback WebSocket handshake rejection as undispatched (`failure_phase = "handshake"`)
- [x] 1.2 Do not bind an account-bound body to the account that refused the upgrade
- [x] 1.3 Regression tests: marker, failover of an account-bound body, dispatched 403 stays bound
