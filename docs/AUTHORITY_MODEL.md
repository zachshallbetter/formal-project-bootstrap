# Authority Model

## Principle

Authority is the right to cause a protected effect under scope.

```text
CAPABILITY != PERMISSION != EVIDENCE != QUALIFICATION != PROMOTION AUTHORITY
```

Tool access, repository access, model capability, expertise, confidence and peer consensus do not create authority.

## Effect classes

```text
E0  observational
E1  reversible internal mutation
E2  reversible/compensable operational mutation
E3  consequential external commitment
E4  durable/irreversible effect
```

Projects may refine these classes but must not silently weaken a higher-level protected effect.

## Minimum generic authorities

A project should bind effects rather than proliferating role names.

```text
project mutation
qualification
promotion
production operation
deviation
```

Domain profiles add only the authorities they actually need.

## Protected-effect rule

An operation is applicable only when all are true:

```text
operation exists
∧ current state permits it
∧ dependencies permit it
∧ actor has scoped authority
∧ budget permits it
∧ required evidence/checks exist
∧ recovery requirements are satisfied
```

Technical possibility is irrelevant.

## Human deviation

A human may intentionally change the governing state. The safe form is a recorded deviation:

```ts
interface Deviation {
  id: string;
  authorityRef: string;
  ruleRef: string;
  reason: string;
  scope: string[];
  allowedEffects: string[];
  createdAt: string;
  expiresAt?: string;
  recovery?: string;
  evidenceRequired?: string[];
}
```

A deviation does not rewrite the original rule. It is bounded, owned, visible and closable.

## Failure

If an effect is possible but unauthorized:

```text
AUTHORITY_MISSING
mutation = none
record blocker
release/park claim
continue unrelated Ready work
```
