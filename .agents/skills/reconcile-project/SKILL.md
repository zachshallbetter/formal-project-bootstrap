---
name: reconcile-project
description: Use at project/session start, after material source changes, after external provider changes, or when state may be stale. Reconstructs current state read-only before mutation.
---

# Reconcile Project

1. Verify project/profile/formal-source identity.
2. Verify repository, branch, commit, submodules and dirty state.
3. Verify context lock and regenerate if stale.
4. Refresh live work graph, claims, provider state, evidence and blockers.
5. Record contradictions and null-result limitations.
6. Do not repair in the reconciliation pass.
7. Return the current lawful Ready frontier and global stop state.
