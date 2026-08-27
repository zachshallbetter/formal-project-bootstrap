---
name: operate-frontier
description: Use to autonomously execute Ready work across a project. Handles selection, claim, isolation, bounded execution, localized blockers, release and frontier reselection.
---

# Operate Frontier

1. Reconcile.
2. Select a Ready, unclaimed, dependency-satisfied item within authority/budget.
3. Claim and isolate.
4. Compile issue context from current context lock.
5. Execute the smallest correct change.
6. On a local blocker: record, release/park, notify affected peers, reselect.
7. On a global stop: prepare the smallest decision packet and stop.
8. On candidate completion: submit for evaluation/qualification required by the issue.
9. Record disposition, release claim and continue.
