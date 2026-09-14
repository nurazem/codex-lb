# Source alignment and validation

Production's Python source matches c0beaaadd96a89f0240582b5449bf4dd50647c7d except seven scoped proxy files. The existing fork patches were reapplied to that baseline, preserving the deployed error response identity and generic 429 normalization changes. No database migrations were added or rewritten.

A consistent read-only logical backup of production restored successfully and passed integrity_check. The rebased application recognizes revision 20260909_070000_automation_run_claim_budget; upgrade head leaves that revision unchanged and the canonical check reports migration_policy=ok and schema_drift=none. The older fork head was rejected by this check and was not deployed.

The earlier fork's full test evidence does not qualify the rebased source. On the rebased tree: 115 route/collector contract tests passed in the first focused run; five HTTP loopback tests exposed a moved transport-selection test interface. After selecting HTTP explicitly and adopting the scheduler seam, all 14 loopback/disconnect/cleanup controls passed. Seven final HTTP progress controls, including native framed-byte visibility, passed. Broader tests and complete image validation are pending.

The deployed source and database backup are held privately. No credentials, provider bodies or operator archives are included in this repository.
