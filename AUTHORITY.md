# Authority and Conflict Resolution

**Status:** Canonical repository doctrine  
**Applies to:** the Formal Project Bootstrap repository itself

## Resolution order

When repository artifacts disagree, the first applicable item controls:

1. `AUTHORITY.md` and accepted governance decisions;
2. `AGENTS.md` for execution behavior;
3. versioned normative contracts, schemas, and profile protocol sources;
4. canonical documentation and templates;
5. executable tooling and tests;
6. generated context, package manifests, release archives, examples, and other derivatives.

External protocols bound by a project retain their own internal authority. This repository does not silently rewrite them.

## Conflict rule

A lower layer may expose a contradiction but cannot resolve it by changing the meaning of a higher layer. Record the conflict, preserve evidence, and either correct the lower layer or approve a normative change at the controlling layer.

Generated artifacts never become authority by convenience. Edit the canonical source and regenerate.

## Evidence

Evidence is orthogonal to precedence. New evidence may challenge doctrine and trigger review, but evidence does not silently mutate the definition it evaluates.

## Supersession

A normative replacement must identify the artifact it supersedes, compatibility impact, migration rule when required, and retained provenance. Historical releases remain immutable evidence.
