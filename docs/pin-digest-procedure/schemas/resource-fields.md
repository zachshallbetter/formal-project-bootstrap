<!-- Proposed additions to schemas/formal-resource-manifest.schema.json -->

Two optional fields on each entry of `resources` (the record already permits
additional properties, so this is documentation of intent rather than a
loosening):

```json
"digestProcedure": {
  "type": "string",
  "description": "Identifier of the procedure that produced revisionOrDigest, e.g. fpb-aggregate-v1. A sha256 pin without this is unverifiable: it cannot be reproduced, and so cannot be refuted."
},
"digestFileCount": {
  "type": "integer",
  "minimum": 0,
  "description": "Number of files the procedure hashed. Not authoritative — a cross-check that makes a wrong mount or a wrong exclusion set visible without rerunning the walk."
}
```

A consuming project that restamps an unreproducible digest should preserve the
previous value rather than discard it; the old value is the evidence that the
pin never held.
