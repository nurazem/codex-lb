# Identity-safe terminal output reconstruction

Empty upstream terminal outputs are backfilled from an index-keyed collector. When completion indexes drift, this retains stale registrations, overwrites completed items and duplicates function identities. Reconcile uniquely identified completions to their registered slot without changing wire events. Reject ambiguous identity, occupied target slots, type changes and conflicting repeated completions. Preserve existing nonempty terminal output and native-route behavior.
