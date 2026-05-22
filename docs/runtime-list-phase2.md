# Runtime List Phase 2 — Immutable Update Operations

Historical implementation note:

The current Nicole specification may differ from this phase document.
Normative language behavior is defined by the spec repository.

Runtime List Phase 2 extends Runtime List Core (`v0.6.0-runtime-list-core`) with immutable update operations on tuple-backed runtime lists.

The execution model is unchanged:

```python
checked = analyze_program(source, host_contract=host_contract)
run_export(checked, "@app.run", runtime_bindings)
```

The runtime still consumes only `CheckedProgram`.
It does not re-parse, re-resolve, or re-check source at runtime.

## Scope

This specification documents only:

- Phase 2A: `list.push` as a historical implementation experiment, not active Nicole v1 language surface
- Phase 2B: `list.set`

`list.pop` is intentionally deferred from Phase 2 implementation scope and is not active Nicole v1 language surface.
No higher-order collection operations are included in this phase.

## Runtime Representation

Runtime list representation remains:

```text
List<T> -> tuple
```

All Phase 2 operations must preserve immutable tuple semantics.

## Phase 2A — `list.push`

Type:

```text
List<T> T -> List<T>
```

Semantics:

- pop value
- pop list
- validate runtime `List`
- return a new tuple with value appended

Examples:

```text
[]:List<Int> 10 list.push
-> (10)

[1,2] 3 list.push
-> (1,2,3)
```

Rules:

- original list is unchanged
- tuple concatenation is acceptable
- no mutation
- no element type inspection
- no homogeneity validation

## Phase 2B — `list.set`

Type:

```text
List<T> Int T -> Result<List<T>, ListError>
```

Semantics:

- pop value
- pop index
- pop list
- validate index as runtime `Int`
- validate list as runtime `List`
- if `0 <= index < len(list)`, return `Ok(new_tuple_with_replacement)`
- otherwise return `Err(OutOfBounds)`

Valid example:

```text
[10,20,30] 1 99 list.set
-> Ok((10,99,30))
```

Invalid cases:

```text
index < 0
index >= len(list)
```

Invalid result:

```text
Err(OutOfBounds)
```

Rules:

- returns a new tuple
- original list is unchanged
- no Python mutation leakage

## Deferred — `list.pop`

`list.pop` is intentionally deferred from Runtime List Phase 2 and remains outside the active Nicole v1 language surface.

Reason:

- immutable pop should return both the updated list and the removed value;
- NicolePy does not yet have a dedicated product/record runtime representation for that result;
- raw Python tuples are already used to represent `List<T>`;
- using `(List<T>, T)` as a raw tuple would blur the distinction between product values and list values.

Future work should first define a product/record representation or another explicit return convention before implementing `list.pop`.

## Error Model

Controlled collection failures return:

```text
Err(OutOfBounds)
```

Runtime integrity failures raise controlled `RuntimeError`.

Examples:

- non-`Int` index where an index is required -> `RuntimeError`
- non-list runtime value where a list is required -> `RuntimeError`
- malformed internal runtime value -> `RuntimeError`

Boundary failures must not be converted into `Err(...)` values.

## Architecture Boundaries

This phase must not introduce:

- `list.map`
- `list.fold`
- `list.reduce`
- `list.filter`
- `map.*`
- loops
- iterators
- generators
- VM
- IR
- bytecode
- runtime parser
- runtime checker
- runtime type inference
- runtime stack-effect inference
- collection execution framework
- speculative abstractions

Including:

- `ExecutionContext`
- `CollectionExecutor`
- `IteratorFrame`
- `SequenceRuntime`
- `GenericApplyEngine`

## Explicit Non-Goals

This phase does not include:

- higher-order collection operations
- map runtime operations
- generalized iteration helpers

## Required Future Tests (Phase 2 Implementation)

### `list.push`

- empty push
- non-empty push
- nested tuple push
- `RuntimeQuote` push
- immutability

### `list.set`

- valid replacement
- negative index
- index == len
- index > len
- nested value replacement
- `RuntimeQuote` replacement
- immutability

## Deferred Future Tests (`list.pop`)

- non-empty pop
- empty pop
- nested values
- `RuntimeQuote`
- value preservation
- immutability
