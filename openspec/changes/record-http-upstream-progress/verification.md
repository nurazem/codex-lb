# Verification

Application, frontend and Rust source at the final PR head match deployed source
`af041799d2fe6a90786a47c08434444f73beae0f`. Later commits update test expectations
for the preserved contracts and deployment documentation.

Static checks, strict OpenSpec validation, frontend tests (1,275), Rust build/tests
and dependency policy, wheel assets, image vulnerability/schema/startup checks,
Helm lint/render/schema checks, PostgreSQL tests (186), bridge tests (337), and
end-to-end tests (27 with one opt-in skip) passed. The 9,214-case unit/simulation
selection completed in bounded batches with two focused reruns: 9,209 unique
passes, four skips, and one expected failure. The monolithic attempt exited 137
without a result and is not counted as passing.

Integration core shards recorded 741, 753, and 928 passes. One older expectation
included an unrepresentable output item but expected a reconstructed success;
the documented rejection contract remains intact. All 16 relevant route and
reconstruction controls passed after splitting valid and invalid fixtures.

Native wire controls initially had 321 passes. Two fixture callbacks needed the
existing response-identity argument; those passed after correction. Three initial
startup failures passed unchanged. Five persistent macOS failures reproduced on
the unchanged upstream baseline. The corresponding six idle/fallback controls
passed in the actual deployed Linux image; an initial Linux direct-idle failure
also passed unchanged. This does not establish a blanket native-suite pass or a
root cause for the local timing sensitivity. Kubernetes smoke on the rebased tree
and live-provider qualification were not run.

Deployment used the complete amd64 image, retained private rollback/evidence
artifacts, and required no database migration. Final readiness through Caddy
reports the expected running image, healthy database and one active ring member.
Logs are bounded to five 10 MB files. Historical upstream capture gaps and
benchmark outcomes are not rewritten by this instrumentation.
