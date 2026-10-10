## ADDED Requirements

### Requirement: Client prompt_cache_key supplies the upstream session identity

When a Responses request reaches an upstream account over the HTTP stream path
or an HTTP bridge upstream WebSocket, carries a nonblank client-supplied
`prompt_cache_key`, and carries none of the Codex process-session or thread
headers (`session_id`, `session-id`, `x-codex-session-id`,
`x-codex-conversation-id`, `thread-id`), the service MUST forward a
`session_id` header upstream. Its value MUST be a UUID derived
deterministically from the authenticated API key id and the
`prompt_cache_key`, such that the same pair always yields the same value and
different keys or different API keys yield different values.

The derived value MUST be egress-only: it MUST NOT change the account-selection
key, sticky kind, freshness window, failover, bridge session key, durable
aliases, owner lookup, or request-log conversation fields. Every upstream
attempt of the request, including a failover attempt on another account and a
reconnect of the same HTTP bridge session, MUST carry the same derived value.

When the request carries any of those session or thread headers, the service
MUST forward the client's header unchanged and MUST NOT add a derived
`session_id`. When the request has no client-supplied `prompt_cache_key`,
including a request whose key was derived by the proxy and later re-resolved,
the service MUST NOT add a derived `session_id`. Bridge recovery that removes
session aliases before a fresh account MUST NOT add one either.

#### Scenario: same key forwards one session id on one account

- **WHEN** two `/v1/responses` requests with the same API key carry `prompt_cache_key: "conv-1"` and no session headers
- **THEN** both are routed with the same `prompt_cache` affinity to the same account
- **AND** both upstream requests carry the same UUID `session_id`

#### Scenario: different keys or API keys never share a session id

- **WHEN** requests carry different `prompt_cache_key` values, or the same value under different API keys
- **THEN** their derived upstream `session_id` values differ

#### Scenario: explicit session header wins

- **WHEN** a request carries `prompt_cache_key` and a client `session_id` or `thread-id` header
- **THEN** the upstream request carries the client's header value unchanged and no derived `session_id`

#### Scenario: failover keeps the derived session id

- **WHEN** the owning account rejects the first attempt and the request fails over to another account
- **THEN** the replacement attempt carries the same derived `session_id`

#### Scenario: keyless request is unchanged

- **WHEN** a request carries no `prompt_cache_key`
- **THEN** the proxy derives its thread-anchored key as before
- **AND** forwards no derived `session_id`
