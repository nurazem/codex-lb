## 1. Sustained-ratio overload trip

- [x] 1.1 Add `RuntimeState.overload_rate_rejections` and copy it in the opportunistic-admission snapshot
- [x] 1.2 Record every overload-class observation into the ratio window and trip on >= 5 observations that are >= 10% of >= 10 outcomes in the error-rate window
- [x] 1.3 Clear the ratio window with the count windows on any trip
- [x] 1.4 Unit tests: incident-shaped steady refusal trips, busy healthy account does not, minimum rejections, minimum samples, window pruning, escalation across trips

## 2. Force Probe reads the stream

- [x] 2.1 `_send_probe_request` returns `ProbeOutcome` and reads a 2xx SSE body to its terminal frame
- [x] 2.2 `AccountProbeResponse` gains `probe_stream_terminal` / `probe_stream_error_code`
- [x] 2.3 Settlement treats a 2xx with an in-stream failure as a failed probe (HTTP 502)
- [x] 2.4 Unit tests for completed, incomplete, failed, error frame, missing terminal, read timeout, non-2xx; integration test for settlement

## 3. Verification

- [x] 3.1 Focused unit and integration tests green
- [ ] 3.2 Deploy and confirm `Account overload backoff engaged` fires for a refusing account under real traffic
