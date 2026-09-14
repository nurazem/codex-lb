## ADDED Requirements

### Requirement: Rebuilt deployment preserves response identity and generic HTTP 429 classification

A replacement image SHALL preserve the observed upstream response ID when normalizing a stream error, unless the error carries its own explicit response ID. A generic HTTP 429 error SHALL be classified as rate_limit_exceeded without overwriting a more specific error code or type.

#### Scenario: An upstream error follows response creation
- **WHEN** the stream created a response and subsequently emits an error without an explicit response ID
- **THEN** the normalized terminal error retains the created response ID

#### Scenario: Generic error body accompanies HTTP 429
- **WHEN** HTTP status 429 accompanies a generic server or upstream error
- **THEN** the normalized error uses rate_limit_error and rate_limit_exceeded
- **AND** a specific error code or type is preserved
