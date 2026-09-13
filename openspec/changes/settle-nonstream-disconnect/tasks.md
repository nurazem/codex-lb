## Work

- [x] Reproduce a non-streaming ASGI disconnect while the real proxy service waits on a synthetic upstream.
- [x] Observe disconnect during collection through one owned watcher; cancel and await collection, preserving reservation ownership and authoritative terminal settlement.
- [x] Test normal completion, pre-terminal disconnect, concurrent requests and cancellation/cleanup failures without duplicated dispatch or settlement.
- [ ] Validate tests and OpenSpec; synchronize the requirements and archive only after verification.
- [ ] Deploy a patch atop the verified current image, preserving its existing changes; run installed synthetic controls and health checks.
