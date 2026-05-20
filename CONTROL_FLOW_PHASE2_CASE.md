# Control Flow Phase 2: `case`

Historical implementation note:

The current Nicole specification may differ from this phase document.
Normative language behavior is defined by the spec repository.

## 1. Goal

Add minimal runtime support for `case` execution in NicolePy.

This phase must execute already checked `case` nodes directly from AST without introducing a general pattern matching engine.

## 2. Real syntax

Runtime Phase 2 must follow the parser syntax already implemented in NicolePy.

`case` consumes a scrutinee already pushed on the stack:

```nicole
: choose { b:Bool -- n:Int }
  b case
    true => 1
    false => 0
  end
;
```

`Result<T,MapError>` form:

```nicole
: unwrap-map { r:Result<Int,MapError> -- n:Int }
  r case
    Ok(v) => v
    Err(MissingKey) => 0
  end
;
```

`Result<T,ListError>` form:

```nicole
: unwrap-list { r:Result<Int,ListError> -- n:Int }
  r case
    Ok(v) => v
    Err(OutOfBounds) => 0
  end
;
```

Notes from current parser/checker surface:

- `case` has no embedded scrutinee field in AST; the scrutinee is a normal prior stack value.
- Supported pattern families in this repository state are:
  - `_`
  - literals (`true`, `false`, numeric, string)
  - `Ok(name)`
  - `Err(name)`
  - `Err(MissingKey)` / `Err(OutOfBounds)`
  - closed variants as names in matching contexts (`MissingKey`, `OutOfBounds`)

## 3. Canonical execution model

- Scrutinee is already evaluated and on runtime stack before `case`.
- Runtime pops exactly one scrutinee value.
- Runtime tests branches in source/AST order.
- First matching branch wins.
- Runtime executes only that branch body.
- Execution remains direct AST walking.
- No re-check pass is allowed during runtime execution.
- No second runtime pattern model is allowed.
- Runtime must not reorder branches.
- Runtime must not optimize branch order.
- Runtime must not build a dispatch table.
- If no branch matches, runtime must raise `RuntimeError("runtime case match failure")`.

## 4. Runtime Result representation

`case` on `Result` requires a concrete runtime representation.
This phase document keeps a minimal explicit representation sketch:

```python
@dataclass(frozen=True)
class Ok:
    value: Any

@dataclass(frozen=True)
class Err:
    error: Any
```

Examples:

- `Ok(42)`
- `Err(MissingKey)`
- `Err(OutOfBounds)`

Rules:

- `Ok(value)` represents `Ok(T)`
- `Err(MissingKey)` represents the closed language variant `MissingKey`
- `Err(OutOfBounds)` represents the closed language variant `OutOfBounds`
- `MissingKey` and `OutOfBounds` are closed language variants, not string payload conventions
- no tuple representation such as `("Ok", value)`
- no dict representation such as `{"tag": "Ok", "value": value}`
- no generic ADT runtime engine
- no second runtime signature/type system

This representation is local to the direct AST interpreter.

Minimal runtime matching rules:

- `Ok(v)` pattern:
  - match condition: `isinstance(scrutinee, Ok)`
  - binding: `v = scrutinee.value`
- `Err(e)` pattern:
  - match condition: `isinstance(scrutinee, Err)`
  - binding: `e = scrutinee.error`
- `Err(MissingKey)` pattern:
  - match condition: `isinstance(scrutinee, Err)` carrying the closed variant `MissingKey`
- `Err(OutOfBounds)` pattern:
  - match condition: `isinstance(scrutinee, Err)` carrying the closed variant `OutOfBounds`

If runtime receives an `Err(...)` value carrying an error not matched by any branch, matching must fail explicitly with:

`RuntimeError("runtime case match failure")`

## 5. Static / runtime boundary

The static checker is authoritative for:

- exhaustiveness
- pattern validity against scrutinee type
- inter-branch stack compatibility
- stack discipline
- domain validity of closed variants:
  - `MissingKey` only for `MapError`
  - `OutOfBounds` only for `ListError`

Runtime must consume only this already validated structure.

Runtime must not perform runtime exhaustiveness checking.
Runtime must not revalidate checker-only domain rules.
Runtime matches concrete runtime values only.

## 6. Explicit non-goals

- No general ADT pattern engine
- No custom destructuring engine
- No runtime exhaustiveness checking
- No runtime type inference
- No dynamic pattern dispatch framework
- No VM
- No IR
- No bytecode

## 7. Required tests

Required runtime tests for this phase:

- bool `case`: `true` branch
- bool `case`: `false` branch
- `Result` `Ok(...)` and `Err(...)` flow
- `MapError` variant handling with `MissingKey`
- `ListError` variant handling with `OutOfBounds`
- nested `case`
- `case` branch calling Nicole words
- `case` producing stack outputs
- host returns `Ok(value)`, `case` matches `Ok(v)`
- host returns `Err(MissingKey)`, `case` matches `Err(MissingKey)`
- host returns `Err(OutOfBounds)`, `case` matches `Err(OutOfBounds)`
- host returns an unmatched `Err(...)`, runtime fails with `runtime case match failure`
- branch matching follows source/AST order (first matching branch wins)

These tests must use parser-real syntax and run through:

`checked = analyze_program(...)`
`run_export(checked, export_name, runtime_bindings)`

## 8. Failure conditions

Any of the following is a failure for this phase:

- starting `call` work before `case` runtime support is stable
- re-checking exhaustiveness at runtime
- introducing a generic runtime pattern engine
- diverging from checker semantics for pattern acceptance and branch effects
- adding IR/VM/bytecode work inside this phase
- representing `Result` as raw tuples
- matching `Result` through undocumented string conventions instead of `Ok` / `Err` runtime classes
- silently accepting unmatched closed-error cases
- selecting an implicit default branch when no branch matches
- suppressing no-match runtime errors

## 9. Next boundary

After `case`, the next high-risk boundary is `call`.

`case` executes branch selection over already checked, finite pattern forms.
`call` introduces runtime execution of quotation values and therefore dynamic control transfer.
This is riskier because it expands runtime dispatch semantics beyond direct word/operator/branch execution.

`call` must not be started from inside `case` implementation work.

## 10. Required report

When this phase starts implementation, the report must include:

- file created
- real syntax confirmed
- supported forms identified from parser/checker
- intentionally excluded points
- ambiguities found in checker behavior
- decisions required before runtime Python implementation

Current pre-implementation report baseline:

- file created: `CONTROL_FLOW_PHASE2_CASE.md`
- real syntax confirmed from parser/tests: `scrutinee case ... end` with `=>` branch arrows
- supported forms identified:
  - bool literal branches
  - wildcard
  - `Ok(name)`
  - `Err(name)`
  - `Err(MissingKey)` for `Result<_,MapError>`
  - `Err(OutOfBounds)` for `Result<_,ListError>`
  - closed variant names `MissingKey` and `OutOfBounds` in matching contexts
- intentionally excluded:
  - general pattern engine
  - dynamic dispatch framework
  - runtime exhaustiveness checks
  - IR/VM/bytecode
- checker ambiguities to decide before runtime implementation:
  - non-exhaustive `case` on scrutinee types outside Bool and supported Result error domains can currently pass static exhaustiveness checks; runtime behavior must still follow checker output as authoritative
  - parser currently accepts both `Err(Variant)` and name variant patterns; runtime matching rules must choose one deterministic interpretation aligned with checker binding semantics
  - concrete runtime source for `Ok(...)` / `Err(...)` host values must be defined in host binding tests before implementation without redefining closed variants as string payload conventions
