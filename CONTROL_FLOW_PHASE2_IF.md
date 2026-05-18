# Control Flow Phase 2: `if`

This document defines the minimal runtime scope for `if` in NicolePy.
It is intentionally narrow.

## Goal

Add runtime execution support for `if` only, using the already checked AST.

## Source of truth

The normative source of truth remains the external Nicole specification repository.

The executable input for this phase remains the already checked NicolePy surface:

`CheckedProgram -> run_export(...)`

Runtime execution must not re-parse, re-resolve, or re-check source code.

## Real syntax

The parser syntax already implemented by NicolePy is:

```nicole
: main { flag:Bool -- }
  flag if
    "yes" host.log
  else
    "no" host.log
  end
;
```

The condition is already on the stack before `if`.
The runtime must pop one `Bool` condition and execute exactly one branch.

## Scope

Phase 2 supports:

- `if`

Phase 2 does not support:

- `case`
- `call`
- runtime quotations
- loops
- closures
- indirect dispatch
- IR lowering
- VM dispatch

## Runtime invariants

- runtime executes the checked AST directly
- runtime trusts the static checker for branch stack equality
- runtime must not introduce a second type model
- runtime must not add fallback behavior
- runtime must not re-check branch types

## Failure conditions

Any of the following is a failure for this phase:

- re-parsing inside `run_export`
- re-resolving inside `run_export`
- re-checking inside `run_export`
- adding `case` support
- adding `call` support
- adding runtime quotations
- introducing IR / VM / bytecode

## Required tests

The phase must be covered by tests for:

- `if true` executes the `then` branch
- `if false` executes the `else` branch
- `if` can call a Nicole word
- `if` can produce stack outputs
- nested `if` with one level of nesting

## Scope reference

Phase 2 begins only after the static core and Runtime ABI Phase 1 remain intact.
