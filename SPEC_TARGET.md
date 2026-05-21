# NicolePy Spec Target

Current target specification:

- tag: v0.17.0-case-guards-spec
- commit: 94240eceff7a6b8d925011f37e80c708c24c72c9

Implementation baseline:

- implementation tag: v0.14.2-workspace-alignment
- implementation commit: 51a22f69ad78a0e8e65787fb38a44d55daf5218d

Conformance status:

NicolePy implements the v0.16.0 direct self-tail-call guarantee.
NicolePy implements the v0.17.0 guarded case branch semantics.

Current state:

- direct self-recursive tail calls are marked statically
- runtime optimization applies to marked direct self-tail-calls
- Nicole call-stack behavior is constant for these calls
- no syntax change introduced for self-tail-call support
- guarded case syntax is implemented: `pattern when guard => body`
- guard evaluation happens only after a successful pattern match
- pattern bindings are visible in the guard
- guard must produce exactly `Bool`
- guard context is pure; dirty calls are rejected statically
- `?` is forbidden in guards
- guarded branches are conditional and do not provide unconditional exhaustiveness coverage
- `_ when guard` is allowed and remains non-exhaustive

Known implementation gaps include:

- no optimization guarantee for mutual recursion
- no optimization guarantee for indirect recursion
- no optimization guarantee for recursion through quotations
- native/Python stack behavior remains outside the Nicole spec contract

Nicole specification remains the only language source of truth.
