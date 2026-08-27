# Formal Resources

Formal resources are external or project-local bodies of knowledge that materially constrain the project.

They are registered in `FORMAL_RESOURCE_MANIFEST.json`.

## Resource kinds

Typical kinds include:

```text
protocol
PRD
architecture
design-system
token-system
schema-pack
policy
research-corpus
benchmark
reference
```

The list is open. Do not create a new kind when an existing one is sufficient.

## Resource record

A resource records, when applicable:

```text
id
kind
required
version
immutable revision or digest
canonical source
local mount or address
authority role
resource inventory
compatibility standing
```

## Authority is separate from importance

A research corpus can be highly valuable while remaining non-normative.
A schema may be normative for serialization while irrelevant to project strategy.
A generated context corpus is operationally important but never source authority.

Do not collapse these distinctions.

## Pinning

Prefer immutable revisions or content digests. `latest` is not a pin.

If an immutable revision cannot be established, record the limitation instead of fabricating one.

## Missing companions

Do not invent missing schemas, conformance fixtures, companion protocols, or research conclusions to make a resource look complete.

Missing remains explicit until supplied by the resource owner or project authority.
