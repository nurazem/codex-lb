# Preserve deployed response contracts

## Why

The deployed Python tree matches upstream c0beaaadd96a89f0240582b5449bf4dd50647c7d except seven scoped proxy files. The earlier fork was based on an older beta whose database head predates production. A complete rebuild must preserve the deployed configuration, schema and existing response identity and HTTP 429 normalization patches.

## What Changes

Rebase the fork fixes onto that source baseline. Preserve the already deployed response identity and generic HTTP 429 classification patches, along with the completed-output and disconnect fixes. Add the new bounded HTTP attempt diagnostics and cancellation cleanup on that coherent source tree. Do not downgrade or stamp the production database.

## Impact

No new schema or configuration fields. The deployment must pass schema checks against a restored production snapshot and a separate startup before traffic switches. Earlier validation on the old fork does not qualify the rebased build.
