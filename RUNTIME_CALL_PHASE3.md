# Runtime Call Phase 3

## Goal

Define minimal runtime semantics for quotations and `call` in NicolePy without changing the static frontend.

Runtime Call Phase 3 must preserve the canonical pipeline:

```python
checked = analyze_program(source, host_contract=host_contract)
run_export(checked, "app.run", runtime_bindings)
```

Runtime consumes only `CheckedProgram`.

## Scope

This phase specifies only:

- runtime representation of checked quotations
- pushing a quotation value at runtime
- executing `call`
- stack behavior
- local and captured value behavior
- runtime error behavior
- interaction with Nicole word calls
- interaction with `host.*`
- interaction with `if`
- interaction with `case`
- tests expected for later implementation

## Explicit non-goals

- no parser changes
- no lexer changes
- no AST redesign
- no checker redesign
- no new static type rules
- no runtime type inference
- no runtime signature inference
- no runtime re-checking
- no source reparsing
- no IR
- no VM
- no bytecode
- no closures beyond already declared quotation captures
- no speculative abstraction layer
- no optional host fallback
- no runtime implementation of collection builtins (`list.map`, `list.fold`, `list.reduce`)
- no loops

## Runtime quotation representation

A runtime quotation is an opaque runtime value derived from an already checked `QuoteNode`.

The runtime quotation may include:

- checked quote body
- declared captures
- declared inputs
- declared outputs
- captured runtime values for declared captures

The runtime quotation must not include:

- source text for reparsing
- IR
- bytecode
- VM instructions
- analyzer/checker state
- inferred signatures
- dynamic type rules

Minimal representation target:

`RuntimeQuote`

The representation should stay minimal and may directly reuse checked structures when simpler.

## Quotation creation semantics

When runtime encounters a checked `QuoteNode`, it must push one runtime quotation value onto the current runtime stack.

If the quotation declares captures, runtime must pop captured values from the current stack according to the already declared capture order used by static checking.

Runtime must not run a second checker pass on quotation captures.
Only minimal runtime shape checks already consistent with the current runtime boundary are allowed.

## `call` semantics

`call` must:

1. Pop one value from the runtime stack.
2. Require that value to be a runtime quotation.
3. Pop quotation inputs from the current runtime stack according to the quotation input list.
4. Execute the quotation body using:
   - current runtime word index
   - current runtime host bindings
   - local environment containing declared captures and call inputs
5. Push quotation outputs onto the caller runtime stack.
6. Propagate runtime errors normally.
7. Not invoke analyzer logic.
8. Not invoke checker logic.
9. Not parse source.
10. Not build IR, VM instructions, or bytecode.

## Stack behavior

`call` consumes the quotation value.

Example:

```nicole
1 2 :[ | x:Int y:Int -- z:Int | x y + ;] call
```

Resulting top of stack:

```text
3
```

## Local environment behavior

Runtime scopes must remain distinct:

- word parameters
- case branch bindings
- quotation captures
- quotation call inputs

Quotation body resolution must continue to rely on existing resolved local names.

Branch-local case bindings must stay branch-local and must not escape.

Quotation execution must not mutate caller locals.

## Error behavior

Runtime must provide controlled errors for:

- `call` on non-quotation value
- malformed runtime quotation value
- runtime stack underflow
- host callable exception
- missing host binding
- runtime case match failure
- unsupported runtime features that remain out of scope

This phase must not introduce a second typechecker.

## Interaction with existing runtime features

Quotation bodies may contain already supported runtime constructs:

- literals
- supported stack operators
- supported arithmetic operators
- Nicole word calls
- `host.*` calls
- `if`
- `case`
- existing `Ok(value)` / `Err(error)` runtime values

Unsupported constructs remain unsupported even inside quotations.
If a quotation body uses an unsupported construct, runtime must fail with controlled runtime errors consistent with the existing style.

## Tests for later implementation

1. quotation literal is pushed as a runtime quotation value
2. `call` executes a quotation returning a literal
3. `call` executes arithmetic
4. `call` executes a quotation with one input
5. `call` executes a quotation with multiple inputs
6. `call` executes a quotation with multiple outputs
7. `call` executes a quotation that calls a Nicole word
8. `call` executes a quotation that calls `host.*`
9. `call` executes a quotation containing `if`
10. `call` executes a quotation containing `case`
11. captured values are available inside the quotation body
12. captured values do not mutate caller locals
13. nested quotation values are not automatically executed
14. `call` on non-quotation gives a controlled runtime error
15. unsupported builtins inside quotations still fail at runtime
16. no parser/checker behavior changes
17. no IR/VM/bytecode files or abstraction layers introduced

## Phase boundary

Runtime Call Phase 3 is a runtime-only extension over the current checked AST pipeline.
It must preserve current architecture and static/runtime boundaries.
