# Versioning

The repository follows Semantic Versioning for the **Formal Project Bootstrap release**.

- **Major:** breaks the bootstrap contract, generated-project shape, required schemas, or operating invariants.
- **Minor:** adds backward-compatible repository capability, schema fields, profiles, checks, or tooling.
- **Patch:** corrections that restore stated behavior without changing the contract.

The canonical release version is the contents of `VERSION`. Tooling reads it; do not duplicate a hard-coded version in executable code.

## Independent external versions

Pinned protocols, profiles, and project bindings keep their own versions. A Formal Project Bootstrap release does not imply that CALP, PGP, IEPE, FE, SES, or any other bound source shares its version or maturity.

## Compatibility is explicit

Matching version numbers never imply cross-layer compatibility. When a project imports another formal source, declare syntax, schema, behavior, semantic, authority, and evidence compatibility in the binding/manifest.

## Generated context

Generated context has no independent semantic version. It is identified by generator version, aggregate source digest, and repository-state provenance.
