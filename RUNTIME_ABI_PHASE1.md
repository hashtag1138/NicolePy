# Runtime ABI Phase 1

This document defines the smallest executable runtime bridge for NicolePy.
It is a chantier spec, not an implementation plan for a VM or a general interpreter.

## Goal

Provide the smallest executable bridge between Nicole exports and Python host bindings.

Language-level effect rules still apply:

- `export` implies `pub`
- `export` does not create dirty effect
- `export` preserves inferred effect
- a pure export cannot call dirty code
- a dirty export is valid only when its body is inferred dirty

The Nicole export syntax for Phase 1 is:

```nicole
export : app.run { -- }
  "hello" host.log
;
```

Minimal typed export example:

```nicole
export : app.add { a:Int b:Int -- result:Int }
  a b +
;
```

The intended shape is:

```python
checked = analyze_program(source, host_contract=host_contract)
run_export(checked, "app.run", runtime_bindings)
```

`run_export(...)` must consume the already checked program surface.
It must not re-parse, re-resolve, or re-check the source.

This phase must execute exported Nicole code against Python host callables without introducing a second runtime type model.

## Source of truth

The normative source of truth for the Nicole language is the external Nicole specification repository.

Runtime ABI Phase 1 does not interpret the specification directly.
It consumes the already checked static surface produced by NicolePy:

`analyze_program(...) -> CheckedProgram`

For this phase, `CheckedProgram`, `SignatureNode`, `TypeNode`, `QuoteTypeNode`, `HostContract`, and `ExportContract` are the executable source of truth for runtime behavior.

This means:

- the runtime must not re-parse, re-resolve, or re-check source code
- the runtime must not introduce a second type or signature model
- any divergence between NicolePy static analysis and the official spec must be fixed in the static frontend first, not patched in the runtime

In short:

- normative truth: Nicole specification repository
- executable runtime input: NicolePy `CheckedProgram`

## Explicit non-goals

- No IR
- No VM
- No bytecode
- No general interpreter
- No fallback OPTIONAL host bindings
- No async runtime
- No new type system
- No runtime module system
- No optimizer
- No code generation

## Canonical execution path

The canonical flow is:

`analyze_program(...) -> ExportContract -> RuntimeHostBindings -> run_export(...)`

The static type model remains the one from the compiler frontend:

- `TypeNode`
- `QuoteTypeNode`
- `SignatureNode`

ABI value boundary reminder:

- `Quote<{ ... }>` and `DirtyQuote<{ ... }>` are not ABI-compatible v1 values and must not cross the host boundary.

Within NicolePy runtime execution, `SignatureNode` is the single executable source of truth for ABI derivation.
The normative language source remains the external Nicole specification.

## Execution model

Phase 1 uses a direct AST interpreter.

Execution walks the already checked AST directly.

There is no IR lowering step.
There is no bytecode generation.
There is no VM dispatch loop.

This is intentional.
The purpose is to validate the runtime ABI bridge first.

## Minimal supported runtime features

Phase 1 runtime support is limited to:

- runtime stack
- literals
- simple builtins: `drop`, `dup`, `swap`, and the strict arithmetic primitives already accepted statically
- host calls: `host.*`
- Nicole word calls
- export lookup

Phase 1 does not include:

- `if`
- `case`
- runtime quotations
- `call`
- loops
- complex collection runtime

## Runtime invariants

- runtime behavior must derive from the static ABI
- no duplicated runtime signature model
- no `TypeRef`
- no second `Signature`
- no runtime fallback for optional host words
- no runtime guessing about missing ABI information

Host contract metadata requirements for v1:

- `signature` is mandatory
- `availability` is mandatory
- `effect` is mandatory and must be `pure` or `dirty`
- there is no implicit default effect
- `effect` is independent from `required`/`optional`
- direct calls to optional host words remain invalid in v1
- `dirty host.foo { ... }` is not Nicole source syntax

Reference shape:

```text
host.log
signature:
{ msg:String -- }
availability:
required
effect:
dirty
```

```text
host.timezone
signature:
{ -- tz:String }
availability:
required
effect:
pure
```

## Required tests

The phase must be covered by tests for the following concrete cases:

### Minimal host call

```nicole
export : app.run { -- }
  "hello" host.log
;
```

This must cover:

- valid host call
- missing host binding
- missing export

### Typed arithmetic export

```nicole
export : app.add { a:Int b:Int -- result:Int }
  a b +
;
```

This must cover:

- wrong arity
- wrong runtime signature

### Export calling multiple host words

```nicole
export : app.process { msg:String -- n:Int }
  msg host.log
  host.random-int
;
```

This must cover:

- Nicole word calling a host word
- multiple host words in one export

## Failure conditions

Any of the following is a failure for Phase 1:

- starting IR before `host.log` works
- introducing a VM before the runtime ABI bridge works
- adding a second runtime type/signature model
- allowing direct OPTIONAL host calls
- allowing runtime fallback behavior
- re-running parse/resolve/check inside `run_export`

## Scope reference

This phase starts from the static core already tagged as `v0.1.0-static-core`.
The runtime work begins only after that static surface is preserved.
