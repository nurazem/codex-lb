## ADDED Requirements

### Requirement: Sustained overload ratio trips the overload window

In addition to the 120-second count window, the balancer MUST record every overload-class observation that reaches the overload window (explicit `server_is_overloaded` / `overloaded_error` rejections and bare `server_error` stream terminals alike, each counted once and unweighted) in a replica-local ratio window whose horizon equals the error-rate window (600 seconds). The overload window MUST also trip when the ratio window holds at least 5 observations, the account's recorded outcomes in the error-rate window number at least 10, and the observations are at least 10% of those outcomes; when the observation being recorded is not yet reflected in the outcome window, the outcome count used MUST NOT be less than the observation count. A ratio trip MUST behave exactly like a count trip: the same level increment, deadline, decay, isolation escalation, log line and candidate-pool rules. Every trip, by either rule, MUST clear the count windows and the ratio window together. The ratio window MUST NOT be reset by successes and MUST NOT change the failure classification, the failover decision, the transient error penalty or the error-rate weight.

#### Scenario: Steady refusal at modest traffic trips the window

- **GIVEN** an account with about four outcomes a minute whose fresh turns are refused about every 100 seconds, so no 120-second window ever holds three weighted rejections
- **WHEN** the fifth refusal inside 600 seconds makes refusals at least 10% of the account's recorded outcomes
- **THEN** the account enters overload backoff at the next level
- **AND** the count windows and the ratio window are cleared

#### Scenario: Scattered rejections on a busy healthy account do not trip

- **GIVEN** an account with about 200 recorded outcomes in 600 seconds
- **WHEN** six overload-class rejections arrive spread across that window
- **THEN** the account is not deprioritized

#### Scenario: Thin evidence never trips the ratio rule

- **GIVEN** an account with fewer than 10 recorded outcomes in the window, or fewer than 5 overload-class observations
- **WHEN** another overload-class observation arrives that does not fill the count window
- **THEN** the account is not deprioritized
