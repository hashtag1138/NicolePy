# NicolePy Spec Target

Current target specification:

- tag: v0.16.0-self-tail-call
- commit: f2c6dfc5de817423c41f1f8060bdd1656b7b63a5

Implementation baseline:

- implementation tag: v0.14.2-workspace-alignment
- implementation commit: 51a22f69ad78a0e8e65787fb38a44d55daf5218d

Conformance status:

NicolePy implements the v0.16.0 direct self-tail-call guarantee.

Current state:

- direct self-recursive tail calls are marked statically
- runtime optimization applies to marked direct self-tail-calls
- Nicole call-stack behavior is constant for these calls
- no syntax change introduced for self-tail-call support

Known implementation gaps include:

- no optimization guarantee for mutual recursion
- no optimization guarantee for indirect recursion
- no optimization guarantee for recursion through quotations
- native/Python stack behavior remains outside the Nicole spec contract

Nicole specification remains the only language source of truth.
