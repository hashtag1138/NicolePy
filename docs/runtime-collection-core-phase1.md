# Runtime Collection Core Phase 1

Historical implementation note:

The current Nicole specification may differ from this phase document.
Normative language behavior is defined by the spec repository.

Runtime Collection Core Phase 1 defines the smallest runtime collection bridge that fits the current direct-AST runtime. It keeps the existing execution model intact:

```python
checked = analyze_program(source, host_contract=host_contract)
run_export(checked, "@app.run", runtime_bindings)
```

The runtime still consumes only `CheckedProgram`.
It does not re-parse, re-resolve, or re-check source.
There is no IR, VM, bytecode, or runtime checker in this phase.

## Goal

Add minimal runtime support for collection values and a small set of pure list builtins.
The runtime must stay direct and conservative:

- immutable list semantics
- copy-on-write map semantics
- no generalized collection execution engine
- no higher-order runtime collection helpers

## Runtime representation decisions

### Lists

`List<T>` is represented at runtime as a Python `tuple`.

This choice is intentional:

- tuples are immutable
- tuples avoid aliasing and accidental mutation
- tuples keep runtime reasoning simple
- tuples fit the current direct-AST interpreter without extra machinery

### Maps

`Map<K,V>` is represented at runtime as a Python `dict`.

The runtime must treat maps as immutable values from the language point of view:

- runtime builtins must not mutate a map in place
- any operation that changes a map must return a new `dict`
- fully persistent map structures are out of scope for this phase

### Immutability rules

- lists are immutable runtime values
- maps are immutable by contract, even if the underlying representation is a `dict`
- runtime code must not expose aliasing that lets one stack value mutate another

## Forbidden scope

This phase must not introduce:

- `list.map`
- `list.fold`
- `list.reduce`
- `list.filter`
- `list.flat_map`
- higher-order builtin iteration helpers
- runtime quotation iteration helpers
- loops
- lazy evaluation
- iterators
- generators
- generalized closures
- async runtime semantics
- collection execution pipelines
- runtime polymorphic dispatch
- VM / IR / bytecode
- runtime parser / runtime checker
- speculative abstractions
- `ExecutionContext`
- `CollectionExecutor`
- `IteratorFrame`
- `SequenceRuntime`
- `GenericApplyEngine`

## Runtime literals

This phase only documents runtime behavior for literals already accepted by the current frontend.
No new syntax is introduced here.

### Lists

If the parser accepts a list literal, the runtime value is a tuple:

- `[]:List<T>` -> `()`
- `[1, 2, 3]` -> `(1, 2, 3)`

The exact list literal syntax remains whatever the current parser already accepts.
This spec does not redefine syntax.

### Maps

The current repository already has typed empty maps through `map.empty:Map<K,V>`.
At runtime that value is an empty `dict`.

Non-empty map literal runtime semantics are deferred until frontend support is confirmed.
If a future parser form already exists, it must still use `dict`-backed runtime values and the same immutability contract.

## Collection literal evaluation semantics

Collection literals are evaluated before they are packed into their runtime value.
This section fixes the runtime evaluation order for literals already accepted by the current frontend.

### Evaluation model

- list literal elements are evaluated left-to-right
- each element expression must produce exactly one runtime value, as already guaranteed statically
- after all elements are evaluated successfully, the runtime packs them into one tuple

### Atomicity

- if any element evaluation raises a runtime error, the list literal is not produced
- no partial list value is pushed

### Nested values

Nested runtime values are preserved as values:

- nested lists remain tuple values
- runtime quotations remain `RuntimeQuote` values and are not auto-executed
- `Ok(value)` and `Err(error)` remain ordinary runtime values
- host call results are packed after the host call returns successfully

### Runtime boundary

Collection literal evaluation must not introduce:

- new scopes
- runtime parsing
- runtime checking
- runtime signature inference
- IR
- VM
- bytecode
- iterator framework
- collection execution engine

Collection literal evaluation does not call analyzer or checker logic at runtime.
It only executes the already checked AST nodes that make up the literal elements.

## Minimal runtime builtin scope

Required list builtins in this phase:

- `list.len`
- `list.concat`
- `list.get`

Historical implementation note:

`list.contains` is not active Nicole v1 language surface.
If mentioned here, treat it only as a deferred or experimental implementation note.

Optional compatibility builtin if already wired statically and kept trivial:

- `list.contains`

Map builtins are not part of Phase 1 runtime implementation.
They remain future work.

## Runtime semantics

### `list.len`

Type shape:

```text
List<T> -- Int
```

Returns the number of elements in the list.

### `list.concat`

Type shape:

```text
List<T> List<T> -- List<T>
```

Concatenation must preserve order.
It must return a new tuple value.
It must not mutate either input value.

## Runtime List Core Phase 1D — `list.get`

### `list.get`

Type shape:

```text
List<T> Int -- Result<T, ListError>
```

Runtime representation stays tuple-backed:

```text
List<T> -> tuple
```

`list.get` operates only on runtime tuple-backed list values.

Semantics:

- stack before: `List<T> Int`
- runtime execution:
  - `index = stack.pop()`
  - `list_value = stack.pop()`
- stack after valid access: `Ok(value)`
- stack after invalid index: `Err(OutOfBounds)`
- pop index
- pop list
- validate index as runtime `Int`
- validate list as runtime `List`
- if the index is valid, push `Ok(list[index])`
- otherwise push `Err(OutOfBounds)`

The `Result` produced by `list.get` is pushed as a normal runtime value.
It is not automatically unwrapped or pattern-matched.
Programs must use `case` or other explicit Nicole constructs to inspect it.

Indexing is zero-based.

Examples:

```text
[10, 20, 30] 0 list.get -> Ok(10)
[10, 20, 30] 1 list.get -> Ok(20)
[10, 20, 30] 2 list.get -> Ok(30)
```

Out-of-bounds cases:

- index < 0
- index >= len(list)
- empty list access

Examples:

```text
[10, 20, 30] -1 list.get -> Err(OutOfBounds)
[10, 20, 30] 3 list.get  -> Err(OutOfBounds)
[]:List<Int> 0 list.get  -> Err(OutOfBounds)
```

Python negative indexing must not leak into Nicole semantics.

`list.get` must not mutate the list.
Since runtime lists are tuples, no copy is required for successful reads.

Nested values are returned unchanged:

- nested list returns tuple
- runtime quotation returns `RuntimeQuote`
- `Ok(value)` remains `Ok(value)`
- `Err(error)` remains `Err(error)`
- no auto-execution occurs

Malformed runtime values are runtime integrity failures.
They raise controlled `RuntimeError`.
They must not be converted into `Err(OutOfBounds)`.

Examples:

- non-tuple list value -> `RuntimeError`
- non-`Int` index value -> `RuntimeError`

## Runtime error behavior

This phase distinguishes between runtime collection errors and runtime boundary failures.

Controlled runtime collection failures:

- invalid index -> `Err(OutOfBounds)`
- unsupported collection builtin -> `RuntimeError`
- malformed runtime collection value -> `RuntimeError`
- runtime boundary type mismatch -> `RuntimeError`

The runtime boundary remains minimal.
No second runtime checker is introduced.

Unsupported builtins should fail with the repository's existing unsupported-feature style rather than with Python exceptions.

## Architecture boundaries

This phase preserves the current architecture:

- direct AST runtime
- `CheckedProgram`-only execution
- no runtime re-analysis
- no runtime type inference
- no runtime stack-effect inference
- no execution framework
- no hidden VM semantics
- no IR
- no VM
- no bytecode
- no runtime checker
- no runtime parser
- no generic collection executor
- no iterator abstraction
- no generalized collection dispatch

The runtime must not introduce speculative layers such as:

- `ExecutionContext`
- `CollectionExecutor`
- `IteratorFrame`
- `SequenceRuntime`
- `GenericApplyEngine`

## Future phase boundaries

### Phase 2

Likely immutable update operations:

- `list.set`
- `list.push` as a historical implementation experiment, not active Nicole v1 language surface
- `map.set`
- `map.remove`

### Phase 3

Possible higher-order collection builtins, if the runtime architecture justifies them later.

Higher-order builtins are intentionally deferred because they significantly increase runtime complexity.

## Required future tests

The later implementation phase should include tests for:

- list literal elements are evaluated left-to-right
- list literal packs values into a tuple
- nested list literal is preserved as a nested tuple
- quotation inside list is preserved as a runtime quotation and is not called
- `Ok` / `Err` values can be list elements if statically allowed
- runtime error during element evaluation aborts construction
- no partial list is pushed after failed construction
- host call result can be packed into a list
- unsupported element runtime feature fails cleanly
- empty list runtime value
- list literal runtime value
- `list.len`
- `list.concat` order preservation
- `list.get` valid index
- `list.get` invalid index
- `list.get` negative index
- `list.get` empty list access
- `list.get` returns nested tuple unchanged
- `list.get` returns `RuntimeQuote` unchanged
- `list.get` returns `Ok(value)` unchanged
- `list.get` returns `Err(error)` unchanged
- `list.get` malformed index fails cleanly
- `list.get` malformed list fails cleanly
- runtime immutability expectations
- unsupported higher-order builtin runtime failure

## Current limitations

This phase does not implement:

- map runtime builtins
- higher-order list builtins
- runtime iteration over collections
- loops
- VM / IR / bytecode
- optional host fallback
- generalized closure machinery beyond the existing quotation model

The document intentionally stays minimal and does not redefine frontend syntax.
