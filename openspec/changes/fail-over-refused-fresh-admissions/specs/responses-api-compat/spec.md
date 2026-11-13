## ADDED Requirements

### Requirement: A refused WebSocket upgrade does not bind the request body

When upstream answers the WebSocket upgrade for a Responses stream with a non-101 status and the proxy does not fall back to HTTP, the resulting error MUST be marked as an undispatched upstream rejection (`failure_phase = "handshake"`, with the upstream status recorded). The streaming retry loop MUST NOT record the refusing account as the dispatch owner of an account-bound body for such an error, so a request that is otherwise movable fails over under the normal failover decision. The marker MUST NOT grant same-account replay or the dead-route backoff reserved for confirmed pre-dispatch transport failures, and an error from a dispatched HTTP request MUST keep its existing owner binding.

#### Scenario: Account-bound body fails over after a refused upgrade

- **GIVEN** two selectable accounts and a fresh streaming request whose input carries encrypted reasoning
- **WHEN** the first account's WebSocket upgrade is refused with HTTP 403
- **THEN** the request is sent to the second account
- **AND** the 403 is not surfaced to the client

#### Scenario: A dispatched HTTP rejection keeps the body on its owner

- **GIVEN** the same request
- **WHEN** the first account rejects the dispatched HTTP request with 403
- **THEN** the body is not sent to another account and the failure is surfaced

### Requirement: The HTTP stream path fails over an output-free overload refusal

On the HTTP streaming Responses path, when the current attempt may still move to another account (attempts remain, the routing strategy is not `single_account`, the request is not an account/model replacement attempt, and it is not bound to the account by a dispatched body, a required previous-response or turn-state owner, or a file owner) and the request is not a background request, the proxy MUST hold back the output-free prelude instead of forwarding it. The prelude is every upstream frame before the first one that shows the turn is running; a frame shows that when it is a terminal (`response.completed`, `response.incomplete`, `response.failed`, `error`), belongs to an output event family (`response.output_item.*`, `response.output_text.*`, `response.output_audio*.*`, `response.output_tool_call.*`, `response.content_part.*`, `response.text.*`, `response.audio*.*`, `response.refusal.*`, `response.reasoning*`, `response.function_call_arguments.*`, `response.custom_tool_call_input.*`, built-in tool call progress such as `response.web_search_call.*`, `response.file_search_call.*`, `response.image_generation_call.*`, `response.code_interpreter_call*`, `response.mcp_*`), is any `*.delta`, carries output addressing or streamed content (`item`, `item_id`, `output_index`, `content_index`, `summary_index`, `part`, `delta`, `text`), reports output items or billed output or reasoning tokens in its `response` snapshot, or does not parse as an event. Every other frame is held, including the lifecycle frames `response.created`, `response.queued` and `response.in_progress`, `response.metadata` (turn-state headers and moderation, verification or safety-buffering notices), vendor telemetry such as `codex.rate_limits` (sent before `response.created` on every Codex turn over the WebSocket upstream) and `responsesapi.websocket_timing`, and output-free frame types upstream adds later. Held frames MUST be released unchanged and in upstream order. If the next upstream frame after the prelude is a terminal `response.failed` or `error` whose normalized code is `server_is_overloaded` or `overloaded_error` and the terminal reports no output items and no billed output or reasoning tokens, the proxy MUST discard the held prelude, record the refusal against the account's health (including the overload window), exclude the account, and retry the request through normal selection without binding the request body to the refusing account. Any other frame, the end of the stream, a transport failure, or 15 seconds without a further frame MUST release the held prelude unchanged and keep the existing visible, non-replayed handling. Holding MUST NOT delay the release of the attempt's response-create admission slot or same-process ownership publication, which happen when the attempt observes the first upstream frame. A request that cannot move MUST forward its prelude immediately and surface the refusal as before. When no other account can be selected, the client MUST receive one terminal failure carrying the refusal code. Whenever an overload refusal is relayed to the client instead of failed over, the proxy MUST log one `Overload refusal not failed over` line with the request id, the account id and the blocking condition: the attempt's immovability reason (`no_attempts_left`, `single_account`, `account_model_replacement`, `dispatched_payload_owner`, `turn_state_owner`, `input_file_owner`, `previous_response_owner`, `background`), or why the hold was released before the refusal (`released_by_event:<type>`, `hold_expired`, `refusal_reported_output`), or `no_other_account` when the refusal was failed over but no other account could be selected. The line MUST NOT contain request or response content.

#### Scenario: Refusal after the prelude is retried on a healthy account

- **GIVEN** two selectable accounts and a fresh streaming request
- **WHEN** the first account sends `response.created`, `response.in_progress` and then `response.failed` with `server_is_overloaded` and no output
- **THEN** the request is retried on the second account, excluding the first
- **AND** the client receives only the second account's `response.created` and terminal event

#### Scenario: Refusal after output is relayed

- **WHEN** an output item or delta precedes the overload refusal
- **THEN** the refusal is relayed after the prelude and output and the request is not replayed

#### Scenario: A bare server_error or a billed refusal is not replayed

- **WHEN** the terminal after the prelude is a bare `server_error`, or an overload refusal reporting output tokens
- **THEN** the prelude is released and the terminal is relayed without replay

#### Scenario: The hold is bounded

- **WHEN** no further frame arrives within the hold after `response.created`
- **THEN** the prelude is released, and a refusal arriving later is relayed without replay

#### Scenario: A previous-response owner keeps the turn

- **GIVEN** a request whose `previous_response_id` resolves to a required owner
- **WHEN** the owner refuses the turn with `server_is_overloaded` after `response.created`
- **THEN** the request is not moved to another account and the client receives the prelude and the refusal

#### Scenario: Vendor telemetry in the prelude does not end the hold

- **GIVEN** two selectable accounts and a Codex follow-up turn carrying encrypted reasoning, a prior tool call and a `prompt_cache_key`, with no `previous_response_id`
- **WHEN** the first account sends `codex.rate_limits`, `response.created` (optionally `responsesapi.websocket_timing`, `response.in_progress` and another `codex.rate_limits`) and then an output-free `server_is_overloaded`
- **THEN** the request is retried on the second account and the client receives only the second account's frames, in upstream order

#### Scenario: A relayed refusal names its blocking condition

- **WHEN** an overload refusal reaches the client because the attempt could not move, the hold had been released, or no other account was selectable
- **THEN** exactly one `Overload refusal not failed over` line with the blocking condition is logged

#### Scenario: Response metadata and unknown output-free frames do not end the hold

- **GIVEN** two selectable accounts and a Codex follow-up turn with no `previous_response_id`
- **WHEN** the first account sends `codex.rate_limits`, `response.created`, `response.metadata` (or a frame of a type the proxy does not know that carries no output) and then an output-free `server_is_overloaded`
- **THEN** the request is retried on the second account, the client receives only the second account's frames in upstream order, and the first account's turn-state never reaches the client

#### Scenario: Any output frame before the refusal ends the hold

- **WHEN** a frame of an output event family, any `*.delta`, or a frame carrying output addressing arrives after the prelude and before an overload refusal
- **THEN** the held prelude is released in order, the refusal is relayed without replay, and the log names `released_by_event:<type>` of that frame
