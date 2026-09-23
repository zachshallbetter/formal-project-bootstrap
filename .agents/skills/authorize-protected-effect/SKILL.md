---
name: authorize-protected-effect
description: Use before any governed effect (push to a protected ref, merge, deploy, history rewrite, default-branch change, transfer, credential or policy change) when the project binds acp-gateway. Obtains the ACP decision, performs only what it authorizes, and disposes of every other decision without stopping the project.
---

# Authorize Protected Effect

1. Resolve the operation to an ACP action via `contracts/acp-protected-effects.yaml`. Not governed → proceed under the work item's own permissions.
2. Identify: provider/account, repository owner+name, remote URL, ref, current (`old_sha`) and intended (`new_sha`) revision, requested action, work item, claim.
3. Load `ACP_GATEWAY_URL` and `ACP_GATEWAY_TOKEN` from the environment or `.env.local`. Never print, log, or compile them.
4. Report first when required (`reportBeforeProtectedEffect`): `POST /internal/report` with the observed protected-artifact state. Reporting grants nothing.
5. `POST /internal/authorize` with `agent_id`, `actor_id`, `repository_claim`, `action`, `context`. Use `--fail-with-body`; a refusal body is actionable.
6. Read `decision` and `reason`; validate against `schemas/acp-decision.schema.json`.
7. Dispose:
   - `ALLOW` → perform exactly `authorized_action` (same action/ref/SHA), once, within the capability TTL; then re-read live state.
   - `AUTH_REQUIRED` → complete the flow named in `auth`; retry once.
   - `RECOVERY_AUTHORIZED` → perform only the described transition, once; `POST /internal/recovery/complete` with the outcome.
   - `DENY` / `REVERIFY_REQUIRED` / `VERIFY_RECOVERY` → do not proceed; record `AUTHORITY_MISSING` with the reason; release or park the claim; reselect.
   - `QUARANTINE` / `LOCKED` → do not proceed and do not repair; preserve candidate and evidence; global stop for this resource; prepare the decision packet.
   - unreachable / malformed / no valid decision → treat as `DENY` with `GATEWAY_UNAVAILABLE`; classify once; do not poll.
8. Record `decision`, `reason`, `request_id`, `policy_id`, `policy_version`, `repository_trust` in the disposition and `records/evidence.jsonl`.
9. Never delegate a refused action to another agent, tool, clone or client to obtain a different answer.
