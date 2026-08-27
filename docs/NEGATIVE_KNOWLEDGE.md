# Negative Knowledge

A project retains useful failures so future workers do not repeatedly rediscover them.

Persist material negative results in `records/negative-results.jsonl`.

A negative result should record:

```text
what was attempted
scope/revision/environment
what failed or was disproven
evidence
consequence
whether the result is local or general
what new evidence would justify reopening it
```

Do not convert an abandoned path into universal doctrine unless the evidence supports that scope.

Do not delete a negative result merely because a later implementation succeeded by a different method.
