# Proposal — define the content-digest procedure, and ship a checker

**Change class:** repository capability (adds tooling and two optional schema
fields; no change to authority, work authorization, evidence semantics, autonomy
boundaries, or context rules).

**Status:** prepared by an agent under owner direction, for maintainer review.
Per `GOVERNANCE.md`, automation may prepare, verify and recommend; it does not
manufacture approval. Nothing here has been applied to a release.

**Prepared against:** formal-project-bootstrap v0.5.1, unmodified.

---

## Problem

`docs/FORMAL_RESOURCES.md` says, under **Pinning**:

> Prefer immutable revisions or content digests. `latest` is not a pin.

and the manifest schema carries `revisionOrDigest`. Neither says how a content
digest is computed. "Aggregate sha256 of the file sha256s over the mount" — the
phrasing consuming projects have adopted — does not determine an answer. It
leaves open which files are walked, which are excluded, what order they are
combined in, and what separator joins them.

A digest whose procedure is unrecorded cannot be reproduced, so it cannot be
refuted. It reads as an integrity control and functions as a decoration. This is
the failure mode `GOVERNANCE.md` guards against from the other direction: a
canonical concept with no mechanism behind it.

## Evidence

From the semantic-cms adoption (`operatingMode: existing`, FPB v0.5.0 profile,
pinning v0.5.1), 2026-08-30:

- Ten resources pinned. `revisionOrDigest` appeared in exactly four places across
  both trees: the manifest, the manifest schema, a generated `llms-full.txt`, and
  one work file. **No script in either project computed or checked a digest.**
- Reproduction was attempted against the `fpb` pin specifically, because its
  source is an immutable released package and drift therefore cannot explain a
  mismatch. **48 candidate procedures** — four exclusion sets, dotfile and
  `.DS_Store` variants, three aggregation forms including the exact form FPB's
  own `gen-context.py` uses — reproduced none of the recorded digest.
- Seven of the ten pins were digests in this state. Two were git revisions and
  verified on first attempt. One is a remote URL with no local mount.

The two that verified are the two whose pin form already had a defined
procedure. That is the whole argument in one line.

## Proposed change

1. **Define one procedure**, `fpb-aggregate-v1`, in `docs/FORMAL_RESOURCES.md`
   under **Pinning** (text in `docs/FORMAL_RESOURCES.pinning.md`). Step 4 is
   deliberately identical to the aggregate in `scripts/gen-context.py`, so the
   repository has one digest idea rather than two.
2. **Add two optional schema fields** to each resource:
   `digestProcedure` (string) and `digestFileCount` (integer). A digest pin
   without `digestProcedure` is reported UNREPRODUCIBLE rather than recomputed
   into agreement — silently restamping an unreproducible pin would erase the
   evidence that it never held.
3. **Ship `scripts/verify-pins.py`**, which verifies git-revision pins by commit
   existence, digest pins by recomputation, and declared inventories by presence.

## Exclusions

- No change to what may be pinned, to authority, or to the repair doctrine.
- No change to existing digest *values*. Restamping is a consuming project's act,
  under its own record, and this proposal deliberately does not automate it as
  part of `make check`.
- Remote pins are reported, not resolved. Fetching a remote source to verify it
  is a separate capability with its own trust questions.

## Limitations — read before adopting

- **This cannot run in CI for path-mounted pins.** Every `canonicalSource` in the
  observed adoption is an absolute path on the owner's machine. A hosted runner
  has none of them, so those pins are verifiable only where the mounts exist.
  The procedure does not fix that; it makes it visible and countable. A project
  that needs CI-verifiable pins must pin by git revision or published package.
- **A restamped digest attests to the source as it is today**, not as it was when
  first pinned. Where the recorded value was unreproducible there is no way back
  to the original state, and the consuming project should keep the prior value
  rather than discard it.
- Six of the observed mounts are directories not under version control. A digest
  over a mutable directory detects drift; it does not prevent it, and it cannot
  say what the drift was.

## Compatibility

Syntax: additive (`additionalProperties` is already true on resource records).
Schema: minor. Behavior: none for existing projects until they restamp.
Authority: unchanged. Evidence: unchanged.

Per `VERSIONING.md` this is a **minor** release: adds backward-compatible schema
fields and tooling.

## Checks run

`scripts/verify-pins.py --self-test` passes, covering: digest match, drift on
content change, drift on file addition, exclusions honoured, unstamped pin
reported UNREPRODUCIBLE, determinism across repeated runs, missing inventory,
remote source, and absent source. Failure was demonstrated by mutation rather
than asserted — zeroing a digest in a real manifest produces DRIFT with a
non-zero exit; restoring it returns to clean.

`make check` in the v0.5.1 tree was **not** run against a modified tree, because
this proposal deliberately does not modify that tree.
