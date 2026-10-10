# Context

## Decision: derive, do not route on, the session id

The fix only adds a wire header. Routing for a client `prompt_cache_key`
already uses the bounded `prompt_cache` sticky affinity, which holds one
account per key until the freshness window lapses or the owner becomes budget
pressured, rate limited, isolated for overload, or unavailable. Turning the
derived id into a routing key would have promoted these requests to durable
`codex_session` ownership, and feeding it into the bridge key would have made
the bridge lane `hard` (`require_same_account` on reconnect), which removes
failover. Both are explicitly rejected by the existing
"Use prompt_cache_key as OpenAI cache affinity" requirement.

Account switches that still happen for one key come from those existing rules.
They are intended; the derived id survives them because it does not depend on
the account.

## Decision: UUIDv5 over (api key id, prompt_cache_key)

- First-party Codex sends a UUID in `session_id`; matching the shape avoids an
  unmeasured upstream format change.
- Deterministic, so every turn, every failover attempt and every replica
  produce the same value without shared state.
- The API key id is length-framed into the name, so two API keys that happen
  to use the same `prompt_cache_key` never share an upstream session.
- The namespace is a literal. Changing it cold-starts every such
  conversation's upstream cache.

## Failure modes considered

- Proxy-derived keys: the anchor derivation writes its `v2t-` key back onto
  the payload, so a second resolution of the same body (bridge to HTTP
  fallback, ring forwarding) looks client-supplied. Keys with that prefix are
  refused. A client that sends a `v2t-` key itself keeps today's behaviour.
- Isolated thread cache identity mode scopes `session_id` per account at
  egress on the HTTP path; the derived header is added before that step, so it
  is scoped like a client header.
- Account-neutral bridge recovery strips session aliases and resets the
  affinity policy, so no derived header is added there.

## Example

`POST /v1/responses` with `prompt_cache_key: "conv-42"`, no session headers,
API key id `K`:

- routing: `prompt_cache` sticky row `conv-42`, unchanged;
- upstream headers: `session_id: uuid5(NS, "<len(K)>:K:conv-42")`;
- the same request with `session_id: abc` forwards `session_id: abc`.
