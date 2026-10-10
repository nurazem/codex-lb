# Tasks

## 1. Derivation

- [x] 1.1 Add `_prompt_cache_upstream_session_id` to `affinity.py`: UUIDv5 over
  the length-framed `(api key id, prompt_cache_key)` under a fixed namespace;
  `None` for a missing, blank or proxy-derived (`v2t-`) key or when any Codex
  process-session or thread header is present.
- [x] 1.2 Record the result on `_AffinityPolicy.upstream_session_id` in
  `_sticky_key_for_responses_request`, only for a key the resolver reports as
  client-supplied. It never enters `selection_kwargs`.

## 2. Egress

- [x] 2.1 HTTP stream: pass `_prompt_cache_upstream_headers(headers, payload,
  api_key)` to `core_stream_responses` in `_stream_once`, leaving `headers`
  untouched for owner lookup and logs.
- [x] 2.2 HTTP bridge: add the policy's session id to the headers handed to
  `_create_http_bridge_session`, so the upstream handshake and later
  reconnects carry it; account-neutral recovery resets the policy first.

## 3. Verification

- [x] 3.1 Unit: determinism, UUID shape, per-key and per-API-key separation,
  length framing, explicit-header precedence, keyless and `v2t-` refusal,
  bridge-fallback re-resolution.
- [x] 3.2 Integration (HTTP stream): same key stays on one account and
  forwards one id across turns even after usage favours another account;
  different key gets a different id; per-API-key ids differ; explicit headers
  win; a rate-limited owner fails over with the same id; keyless requests
  forward no `session_id`.
- [x] 3.3 Integration (HTTP bridge): pre-dispatch connect failover reconnects
  with the same id and the follow-up reuses the socket; explicit header and
  keyless requests keep their connect headers unchanged.
- [x] 3.4 Strict OpenSpec validation of this change (`openspec validate <change> --strict`).
