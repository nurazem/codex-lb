# Evidence

Paired upstream and downstream captures show stable item IDs with completion indexes shifted by one. The bytes already differ from the registration upstream; this is not proxy-created drift. Four retained failing prefixes now replay with consistent item indexes. Since the client disconnected, those captures remain truncated failures, not reconstructed successful responses.

114 Responses contract tests, ruff and ty pass. The spec set validates (66 specs). Public wire completion indexes now change as well as terminal backfill; native passthrough is unchanged. No private prompts or tool payloads are committed.
