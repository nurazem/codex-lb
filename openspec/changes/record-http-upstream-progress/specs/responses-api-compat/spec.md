## ADDED Requirements

### Requirement: Non-streaming disconnect cleanup tolerates level cancellation
Non-streaming response collection MUST join its existing cleanup owner without repeatedly cancelling that owner. The join MUST tolerate both repeated task cancellation and a level-cancelled ASGI scope without callback accumulation or a busy loop. It MUST preserve the caller cancellation after cleanup and retain the existing completed-result precedence.

#### Scenario: ASGI cancellation persists during cleanup
- **WHEN** the caller's cancellation scope remains cancelled while owned cleanup waits
- **THEN** unrelated event-loop tasks continue to run
- **AND** the original cleanup completes once before collection exits
