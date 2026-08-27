# Changelog

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
