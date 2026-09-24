# Changelog

## 0.5.3 — ACP client, governed-repository check, reporting contract

- `scripts/acp.py`: stdlib client for every ACP call a project makes —
  `authorize`, `report`, `snapshot`, `verify-capability`, `recovery-complete`,
  `board`, `policy`. Fails closed (unreachable/refused/malformed → synthetic
  `DENY`/`GATEWAY_UNAVAILABLE`), refuses `ALLOW` with
  `policy_effect: NOT_GOVERNED` under `failClosed` (`ACP_NOT_GOVERNING`),
  refuses an `ALLOW` whose `authorized_action` differs from the request
  (`AUTHORIZED_ACTION_MISMATCH`), exits non-zero for every non-`ALLOW`, and
  records decisions without the capability token. Copied by the initializer;
  declared as `authorizationProvider.clientScript`.
- Reporting contract made concrete: the typed events acp-gateway accepts on
  `/internal/report` (`SESSION_STARTED`, `SESSION_RESUMED`,
  `PROTECTED_EFFECT_PENDING`, control-plane-change events) and the
  `/internal/integrity/snapshot` checkpoints, in `docs/ACP_INTEGRATION.md`
  and the action map's new `reports:` section. Requires acp-gateway with
  checkpoint events (0.5.2's "report at session start" had no accepted wire
  shape).
- "Governed" defined: a project is governed only when a policy registered in
  the gateway names the repository. `acp-check.py` now fails its `notice`
  check otherwise (`--allow-ungoverned` to downgrade during onboarding), and
  reads the repository owner from `origin` rather than the board owner.
  `acp.py policy` emits the candidate policy (repository, board, control-
  artifact manifest) for `acp-gateway/scripts/register-policy.py`.
- `capability_token` documented and added to the decision schema (the
  boundary checks the token, not the `capability` object); `synthetic`,
  `gateway_decision` and the synthetic reason codes added.
- Fixed: `contracts/acp-protected-effects.yaml` was not valid YAML in 0.5.2
  (`RECOVERY_AUTHORIZED:{` and siblings). The validator now parses it when
  PyYAML is available.
- Fixed: a global `core.excludesFile` that ignores `AGENTS.md` left it out of
  every commit. The initializer adds `!AGENTS.md`; the validator rejects any
  required file git would ignore.
- Reconciled with a parallel 0.5.3 build (kept for reference as
  `formal-project-bootstrap-v0.5.3-alt`): adopted its `acp.py notice`
  command, exit `5` for "not governed" in `notice` and `acp-check.py`,
  `report --path` (attaches the file's digest), and its broader control
  manifest — ten files including the client scripts, with per-file
  `required`, plus `.agents/skills/**` and `records/deviations.jsonl`
  patterns. Its `changes_require_authorization` default was not adopted:
  nothing yet obtains that authorization, so `authorize_and_report` stays the
  default and `--strict` remains the hard mode.
- Fixed: an inline comment after a `board.env` value (`GH_PROJECT_NUMBER=38 #
  Azimuth`) was read as part of the value.
- Additive for projects on 0.5.2: re-pin, copy `scripts/acp.py`, the updated
  `acp-check.py`, `validate-bootstrap.py`, action map, schema, doc and skills;
  add `"clientScript": "scripts/acp.py"`; register the repository's policy.

## 0.5.2 — ACP authorization provider binding

- Bound `acp-gateway` (Agent Control Plane) as the reference `protection`,
  `authorization` and `telemetry` provider: `docs/ACP_INTEGRATION.md`,
  `contracts/acp-protected-effects.yaml` (effect class → ACP action projection
  and the A0–A7 decision dispositions), `schemas/acp-decision.schema.json`.
- Profile template declares `authorizationProvider` (fail-closed, governed
  from E2, report-on-start / report-before-protected-effect); bindings
  template binds protected effects to `acp-gateway:decision` and elevated
  effects to `acp-gateway:recovery-authorization`.
- `AGENTS.md` §17 external authorization authority; §5 and §9 reference it;
  `NEW_AGENT_PROMPT.md` requires a decision before any governed effect.
- New skill `authorize-protected-effect`; `operate-frontier` and
  `reconcile-project` call it and read the work graph through ACP.
- `scripts/init-project.py --acp-gateway-url/--acp-owner/--acp-project`
  writes `.agents/board.env`, `.env.example` and secret-safe `.gitignore`
  lines; the token is never written. `scripts/acp-check.py` verifies wiring
  (health, auth, owner, board, notice) without printing secrets and can record
  gate `B0-acp`. `validate-bootstrap.py` checks the binding's integrity.
- Doctrine: the ACP decision is the authorizing instrument for governed
  effects; deviations, evidence, reports and claims never substitute for it.
  Agent-side instruction gates only clients that ask; external enforcement
  remains a separate, explicitly recorded binding.
- Additive for projects on 0.5.1: re-pin, add `authorizationProvider` to the
  profile, copy the new doc/contract/schema/skill/script, then validate.

## 0.5.1 — Instrument stratification and upstream-first repair

- Authority model: added instrument stratification — wherever two record types
  attach to one consequential effect, the authorizing instrument is declared and
  the weaker grants nothing; "authorization by the cheaper record" named as an
  illegal pattern (incident provenance: semantic-cms NR-scms-001).
- Formal resources: added consumption model (pinned dependencies; a synced copy
  is a cache of the pin, not a fork), upstream-first repair (re-pin as a
  compatibility event), and upstream debt subordinated to the deviation
  instrument (deviation authorizes first; the debt record references it and
  ages; the ratchet is memory and pressure, never permission).
- Negative knowledge: named two drafting failure classes (authorization by the
  cheaper record; descriptive-to-normative contamination).
- Doc-level, additive release: no schema, script, or required-file changes;
  projects on 0.5.0 re-pin without structural migration.

## 0.5.0 — Existing-project adoption

- Added a first-class existing-project adoption/reconciliation contract.
- Added C4c conformance for non-destructive migration into materially pre-existing projects.
- Clarified that initializer collisions mean admitted-but-unreconciled state, not permission to overwrite project authority.
- Made existing-mode agents discover, preserve, bind, minimally fill gaps, then compile/qualify before normal operation.
- Kept B5–B8 conditional; adoption must not manufacture behavioral evidence.


All notable changes to Formal Project Bootstrap are recorded here.

## [0.4.0] - 2026-08-27

### Added
- complete project-local formal-resource, evidence, negative-knowledge, landing/promotion, recovery, and skills-index definitions;
- `FORMAL_RESOURCE_MANIFEST.json` project artifact and schema;
- persistent project records for evidence, negative results, deviations, and alignment;
- non-destructive `--mode existing` initialization with explicit collision candidates and alignment records;
- explicit conformance distinction between directed cross-project testing (C4a) and behavioral transfer without evaluator restatement (C4b).

### Changed
- B0–B4 remain normal bootstrap proof gates; B5–B8 are conditional operational observations and must not be manufactured during ordinary initialization;
- B6 is now explicitly candidate/landing/evidence separation, B7 multi-agent coordination, and B8 recovery;
- `NEW_AGENT_PROMPT.md` is intentionally thin and no longer restates blocker or peer-coordination response sequences;
- generalized the old protocol-only resource manifest into a formal-resource manifest covering protocols, PRDs, architectures, design/token systems, schemas, policy, research, benchmarks, and references;
- generated projects now retain project-specific record ledgers from initialization.

### Research correction
- directed conformance and spontaneous behavioral transfer are no longer treated as the same claim. A worker that is told the target response may establish conformance but not unprompted transfer.

## [0.3.0] - 2026-08-27

### Added
- repository-grade authority, versioning, governance, contribution, security, and support documents;
- CI and release workflows;
- issue and pull-request templates aligned to evidence and authority rules;
- deterministic release packaging and checksums;
- project initializer;
- repository conformance and release tests;
- explicit repository-state provenance without making generated context self-referential.

### Changed
- version became canonical through `VERSION`;
- context validity became source-digest based while Git state remained provenance.

## [0.2.0] - 2026-08-27

- compressed the bootstrap into a generic formal operating kernel;
- made compiled context required but non-normative;
- added bounded blocker reselection, multi-agent coordination, formal deviations, alignment bindings, and optional commercialization profile.

## [0.1.0] - 2026-08-27

- initial commercialization-oriented project bootstrap candidate.
