# ESP/RCP profile

This profile initializes a project as an unbound External State Protocol instance with an optional Recipient Contract Protocol record.

Use `scripts/esp-record.py <kind> --record '<json>'` to append a typed record. Existing identities are idempotent only when the content is identical; conflicting reuse is refused.

Initialization creates identity and empty append-only ledgers only. It does not invent an owner, recipient, counterparty, campaign, commitment, evidence, receipt, measurement, or learning result.

The external-state instance remains `unbound` and at lifecycle `bootstrap` until project authority supplies those records. RCP status is derived by `scripts/recipient-status.py` from `records/recipient.json` and an explicit as-of date.

Record ownership:

- `records/external-state.json`: ESP instance identity, lifecycle, authority bindings, and ledger paths.
- `records/campaigns.jsonl`: campaigns and external-state objectives.
- `records/commitments.jsonl`: counterparties, obligations, and closure.
- `records/evidence.jsonl`: evidence references and qualification lineage.
- `records/qualifications.jsonl`: EQP qualification dispositions.
- `records/receipts.jsonl`: observed external receipts.
- `records/measurements.jsonl`: reach, authority, adoption, propagation, and position measurements.
- `records/learning.jsonl`: retained learning and negative results.
- `records/recipient.json`: nullable RCP recipient obligation.
