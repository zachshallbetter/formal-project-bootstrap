<!-- Proposed replacement for the "Pinning" section of docs/FORMAL_RESOURCES.md -->

## Pinning

Prefer immutable revisions or content digests. `latest` is not a pin.

If an immutable revision cannot be established, record the limitation instead of
fabricating one.

A content digest is a claim about a source, and a claim that cannot be
reproduced cannot be refuted. Record the procedure alongside the digest, in
`digestProcedure`. A digest pin without one is unverifiable regardless of how it
was produced.

### Procedure `fpb-aggregate-v1`

1. Walk the mount. Skip any path with a component named `.git` or
   `node_modules`, and any file named `.DS_Store`. Skip symlinks.
2. For each remaining file take its mount-relative POSIX path and the sha256 of
   its bytes.
3. Sort by that path in byte order, not locale order.
4. The digest is `sha256` of the entries joined as `path:filehash` by `\n`, with
   no trailing newline.

Step 4 is the aggregate `scripts/gen-context.py` already computes, so the
repository keeps one digest idea rather than two. Steps 1 and 3 are what prose
descriptions leave open, and are why undocumented digests are not reproducible
in practice.

### What a digest does and does not establish

A digest over a mutable directory **detects** drift; it does not prevent it, and
it cannot say what changed. It also says nothing about whether the mount still
contains what the manifest claims to import — check the declared `inventory`
separately.

A pin whose `canonicalSource` is an absolute local path can only be verified on
a machine holding that mount, so such pins cannot be gated in hosted CI. Pin by
git revision or published package where CI verification is required.
