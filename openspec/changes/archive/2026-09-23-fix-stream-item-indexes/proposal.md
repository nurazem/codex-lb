# Repair unambiguous streamed output indexes

Upstream can register an item at N and finish its reasoning or hosted-search lifecycle at N+1 with the same stable ID. Terminal-only reconciliation leaves streaming consumers unable to finish. Canonicalize unambiguous item-scoped events on the public Responses surface; retain native passthrough and reject conflicting slots.
