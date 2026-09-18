# Formal Project Bootstrap

**Status:** Candidate reusable project substrate  
**Version:** 0.5.1

Formal Project Bootstrap creates projects in which agents can operate for long periods with bounded autonomy because intent, authority, work, evidence, context, coordination, and recovery are explicit.

It is deliberately small at the top. It does not define a product domain, business model, UI system, physics model, or research method. Projects bind those things as explicit profiles and formal sources.

## Governing thesis

> **Autonomy increases as consequential ambiguity decreases.**

A project should be able to answer from canonical state:

```text
What are we trying to change?
What is authoritative?
What is true now?
What work is Ready?
What may this actor change?
What evidence is required?
What is unresolved?
What can proceed without the blocked item?
What requires a human decision?
```

The agent is an execution substrate. It is not the source of project truth.

## Operating model

```text
ORIGINATING INTENT
      ↓
FORMAL RESOURCES + PINS
      ↓
PROJECT BINDINGS + AUTHORITY
      ↓
COMPILED PROJECT CONTEXT
      ↓
LIVE RECONCILIATION
      ↓
READY WORK FRONTIER
      ↓
CLAIM + ISOLATION
      ↓
BOUNDED EXECUTION
      ↓
CANDIDATE + EVIDENCE
      ↓
INDEPENDENT EVALUATION
      ↓
QUALIFICATION / PROMOTION
      ↓
RECONCILIATION
      └────────────→ NEXT READY FRONTIER
```

A blocked item terminates or parks that claim, not the project. Unless a global stop condition holds, the coordinator recomputes the Ready frontier and continues lawful work.

## Why compiled context exists

Canonical sources and compiled context are intentionally different things.

Canonical sources include specifications, protocols, PRDs, schemas, design systems, research, source code, tests, decisions, evidence, and work records.

Compiled context consists of:

```text
.agents/llms.txt
.agents/llms-full.txt
.agents/context-lock.json
```

These are required operating artifacts once a project is initialized because they make the formal environment cheap for agents to search and load. They are always generated, rebuildable, non-normative, and downstream of canonical sources.

Context validity is source-digest based. Git branch/commit/submodule state is retained as provenance so agents can bound branch-specific or absence claims without creating an impossible self-reference where a generated file must contain the hash of the commit that contains itself.

> **Never repair authority by editing generated context. Repair the source and recompile.**

## Quick start

Validate this repository:

```bash
python3 scripts/gen-context.py
python3 scripts/check-all.py
```

Initialize a new project:

```bash
python3 scripts/init-project.py \
  --name "My Project" \
  --id my-project \
  --mode new \
  --output ../my-project
```

Add an optional profile only when it is actually required:

```bash
python3 scripts/init-project.py \
  --name "Commercial Project" \
  --id commercial-project \
  --mode new \
  --profile commercialization \
  --output ../commercial-project
```

The initializer creates the project intent/profile, formal-resource state, bindings, persistent evidence/negative/deviation/alignment records, context policy, schemas, operating docs, agent skills, and compiled context; then it runs the project validator. `--mode existing` is non-destructive: conflicting bootstrap candidates are staged for explicit reconciliation rather than overwriting existing authority. Existing-project adoption is a distinct C4c path governed by `docs/EXISTING_PROJECT_ADOPTION.md`: discover existing authority first, reconcile/bind before synthesis, preserve unresolved contradictions, and add only missing operating primitives.

## Core invariants

1. Intent governs implementation.
2. One canonical statement; many references.
3. Pinned formal sources outrank generated context.
4. Chat/tool capability does not silently grant project authority.
5. Committed mutation requires a complete authorized work item or an explicitly recorded deviation.
6. Worker completion does not equal issue promotion.
7. Evidence strength does not grant promotion authority.
8. Candidate authorship and independent evaluation remain separate where practical.
9. Negative, contradictory, partial, and inconclusive results are retained.
10. Blockers are typed and localized; unrelated Ready work continues.
11. Human attention is consumed at decision boundaries, not routine execution boundaries.
12. Agents may communicate, hand off, pause, supersede, and revert their own work; peer agreement does not manufacture authority.
13. Official service CLIs/APIs are preferred operational boundaries when the project profile explicitly authorizes them.
14. Generated context is refreshed from selected canonical sources before consequential work.
15. New abstractions are added only for irreducible distinctions that cannot be represented by binding, specialization, constraint, projection, qualification, or composition.

## Qualification discipline

Normal initialization proves B0–B4. B5–B8 are conditional operational observations and must not be manufactured merely to make a report green. If no legitimate blocker, landing, concurrent worker, or recovery event occurs, record `NOT OBSERVED` / `NOT EXECUTED`.

The bootstrap may define the operating rule being tested. A transfer experiment seeking behavioral evidence should not restate that rule again in the worker prompt. See `docs/BOOTSTRAP_SEQUENCE.md` and `docs/CONFORMANCE.md`.

## Repository structure

```text
AUTHORITY.md                       repository conflict-resolution authority
AGENTS.md                          root project execution contract
GOVERNANCE.md                      normative-change and anti-bloat rules
VERSION / VERSIONING.md            release identity and compatibility policy
PROJECT_INTENT_TEMPLATE.md         originating intent template
PROJECT_PROFILE_TEMPLATE.json      runtime/project bindings template
FORMAL_RESOURCE_MANIFEST.json    pinned formal dependencies
CONTEXT_SOURCES_TEMPLATE.json      deterministic context-source policy
NEW_AGENT_PROMPT.md                thin worker entry prompt
bindings/                          semantic and authority bindings
contracts/                         extension point for project contracts
docs/                              operating definitions, conformance, and retained negative results
schemas/                           machine-readable coordination/context schemas
scripts/                           init, context, validation, and release tooling
tests/                             repository conformance tests
.agents/skills/                    narrow reusable operating procedures
profiles/commercialization/        optional CALP/PGP overlay
.github/                           CI, release, issue, and PR workflow definitions
```

## Conformance

Conformance is layered. Structural success is not operational or empirical validation.

```text
C0 Structural
C1 Context
C2 Bootstrap
C3 Operational
C4a Directed cross-project conformance
C4b Behavioral transfer
C5 Comparative empirical
```

See `docs/CONFORMANCE.md` for the exact boundaries.

## Verification

The complete repository gate is:

```bash
python3 scripts/check-all.py
```

For full YAML/JSON-Schema verification install the optional verification dependencies first:

```bash
python3 -m pip install -r requirements-dev.txt
```

Release artifacts are deterministic:

```bash
python3 scripts/package-release.py --output dist --verify-reproducible
```

A tag `vX.Y.Z` is releasable only when it equals `VERSION`; the release workflow verifies, packages, and publishes the resulting archive, manifest, and SHA-256 file.

## Status honesty

Formal Project Bootstrap v0.5.1 has implemented repository tooling and executable checks. That does **not** establish that the methodology is empirically superior across models, projects, organizations, or domains. Directed conformance, behavioral transfer, and comparative claims require separate qualification. In particular, a worker prompt that restates the target behavior can establish conformance but not unprompted behavioral transfer.

## License

No repository-wide license has been selected yet. See `LICENSE.md`. Bound external resources retain their own licenses regardless of the license eventually chosen here.
