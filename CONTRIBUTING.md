# Contributing

Contributions are welcome when they preserve the bootstrap's central property: a small formal kernel that increases agent autonomy by reducing consequential ambiguity.

## Before changing anything

1. Read `AUTHORITY.md`, `AGENTS.md`, and `GOVERNANCE.md`.
2. Open or select a complete issue.
3. Classify the change as editorial, repository capability, or normative.
4. Prefer the smallest change that closes the evidenced gap.

## Checks

Run:

```bash
make check
```

For a release candidate, also run:

```bash
make package
```

## Pull requests

A pull request should identify the issue, scope, exclusions, evidence, checks run, limitations, compatibility impact, and whether generated context was refreshed.

Normative changes must not be hidden inside implementation or cleanup PRs.
