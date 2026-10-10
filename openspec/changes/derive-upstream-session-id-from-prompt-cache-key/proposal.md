# Change: derive-upstream-session-id-from-prompt-cache-key

## Why

Clients that name each conversation with one stable `prompt_cache_key` and send
no Codex session header (OpenAI SDK clients and agent frameworks on
`/v1/responses`) never get upstream prompt-cache hits through the proxy.
Measured against the upstream Codex backend:

- an identical request with a fixed `prompt_cache_key`, sent five times, never
  reported cached input tokens;
- the same request with a Codex `session_id` header cached from the second call;
- `conversation_id` and `chatgpt-conversation-id` headers had no effect.

Upstream therefore keys prompt-cache reuse on the Codex `session_id` header,
not on `prompt_cache_key` alone. First-party Codex always sends that header;
SDK clients do not, and the proxy forwards inbound session headers verbatim
without ever supplying one.

## What Changes

- When a Responses request carries a client-supplied `prompt_cache_key` and no
  Codex process-session or thread header (`session_id`, `session-id`,
  `x-codex-session-id`, `x-codex-conversation-id`, `thread-id`), the proxy
  forwards a `session_id` header upstream whose value is a UUIDv5 derived from
  the API key id and the `prompt_cache_key` under a fixed namespace.
- The derived header is egress-only. Account routing is unchanged: the
  request keeps the existing bounded `prompt_cache` sticky affinity (same TTL,
  budget reallocation, overload isolation and failover). Owner lookup, bridge
  session keys, durable aliases and request logs keep reading the client's
  headers.
- It is applied on the HTTP Responses stream path (each attempt, so failover
  attempts carry the same id) and on HTTP bridge upstream WebSocket creation
  (stored on the bridge connect headers, so reconnects keep it). Bridge
  account-neutral recovery, which already strips session aliases before a
  fresh account, resets the affinity policy and therefore adds nothing.
- An explicit client session or thread header always wins and is forwarded
  untouched. Requests without a client `prompt_cache_key` are unchanged,
  including when a proxy-derived (`v2t-`) key is re-resolved on the bridge to
  HTTP fallback.

Out of scope: the downstream WebSocket Responses transport (Codex clients there
already send `session_id`), `/responses/compact`, and per-API-key scoping of the
`prompt_cache` sticky row.

## Impact

- Code: `app/modules/proxy/affinity.py`,
  `app/modules/proxy/_service/streaming/mixin.py`,
  `app/modules/proxy/_service/http_bridge/mixin.py`,
  `app/modules/proxy/service.py` (facade re-export).
- Specs: `responses-api-compat`.
- No schema, migration, or setting change. Zero-config and on by default: the
  header first-party Codex already sends is the only thing that makes upstream
  caching work for these clients, so there is nothing an operator should turn
  off.
