# Verification and upstream review

Upstream main 3d23d53f still collects terminal output by raw output_index. Related #542/#543 fixed Chat Completions argument routing, not Responses terminal backfill. #1898/#1900 concern durable replay transcripts; #1900 is closed unmerged. No matching identity-safe terminal reconstruction fix was found in searched issues, PRs, or current main.

112 public-response contract tests pass, including shifted completion, occupied slot, identity/type conflict and conflicting completion controls. Four privately retained failing streams now reconstruct unique completed items in registration order; original events remain unchanged. No raw customer payload is committed. Ruff, focused Ty and diff checks pass. Hosted-search wire-index drift remains upstream and outside this patch.

Integration: 107 passed; test_public_responses_preserves_tool_search_output[False-False] fails on both this patch and unmodified parent 02c94774 (unsupported unknown item in reconstructed non-streaming output). This baseline failure is outside the streaming collector change. OpenSpec validation: 66 specs passed, no failures.
