# Deployment evidence

Production source commit: 14fe7f3a4df5d199dfb62f22dac7faa4a99b9222, merging deployed af041799 and upstream 3d23d53f. Image tag: codex-lb:fork-14fe7f3a. Temporary source bind mounts removed. Archive remains enabled via the existing environment fallback; the new dashboard override is unset.

Focused checks: 1,418 proxy/collection tests passed after updating the fork capacity test for upstream's deliberate recovery wait and its expected generic-429 classification. Another 123 capture/collection/archive/progress checks and 10 selected public Responses checks passed. Changed-file Ruff and wire-capture typing checks passed. Strict OpenSpec change validation passed. These are focused checks, not a claim of full repository CI.

Migration rehearsal on a production SQLite backup preserved 10 accounts, 5 API keys, and 460,537 request-log rows; quick_check passed. Both rehearsal and production reached 20260922_000000_merge_scim_and_overflow_heads. Production health returned HTTP 200. A fresh stopped-process database backup, old image and compose configuration remain for rollback because the upstream migration removes legacy credential columns.

The upstream timestamp collision between two published 20260914_000000 migrations remains a topology-lint violation. The new no-op merge fixes the multiple-head deployment failure without rewriting published identities; the real database upgrade passed. No claim of a fully green topology lint.

Archive files and deployment backups are private and are not checked into git. Runtime/GAIA versions were unchanged for the two-case post-upgrade measurement. Synthetic normalization controls are not attribution of historical upstream errors.
