# Runtime Map Core Phase 1

Historical implementation note:

The current Nicole specification may differ from this phase document.
Normative language behavior is defined by the spec repository.

## Overview

This document specifies the first runtime map support for NicolePy.

The canonical execution model remains:

```python
checked = analyze_program(source, host_contract=host_contract)
run_export(checked, "app.run", runtime_bindings)
```

Runtime consumes `CheckedProgram` only.

There is no runtime parsing, runtime checking, runtime inference, IR, VM, or bytecode.

## Runtime Representation

Runtime maps use the following representation:

```text
Map<K,V> -> dict
```

Maps are immutable by language contract.

Runtime builtin operations never mutate an input dict in place.

Operations that modify a map return a new dict value.

This phase does not introduce a persistent-map structure or mutable alias exposure.

## Map key rule

Nicole v1 defines admissible key types for `Map<K,V>`.

Runtime Map Core Phase 1 therefore follows the Nicole language rule:

Runtime Map Core Phase 1 accepts only runtime values of type:

- `Int`
- `String`
- `Bool`

as map keys.

This is a Nicole language rule in v1, not merely a runtime implementation restriction.

## Runtime Map Core Phase 1A

### `map.empty`

Type:

```text
Map<K,V>
```

Semantics:

- produces an empty runtime dict
- the result is an ordinary runtime value

### `map.get`

Type:

```text
Map<K,V> K -> Result<V,MapError>
```

Semantics:

- if the key exists, return `Ok(value)`
- if the key is missing, return `Err(MissingKey)`
- the returned `Result` is an ordinary runtime value
- the stored value is returned as-is

### `map.contains`

Type:

```text
Map<K,V> K -> Bool
```

Semantics:

- return `true` when the key exists
- return `false` when the key is missing
- the result is an ordinary runtime value

## Runtime Map Core Phase 1B

### `map.set`

Type:

```text
Map<K,V> K V -> Map<K,V>
```

Semantics:

- return a new dict with the key associated to the new value
- do not mutate the original dict
- do not expose mutable aliasing
- stored values are preserved as runtime values

### `map.remove`

Type:

```text
Map<K,V> K -> Result<Map<K,V>,MapError>
```

Semantics:

- if the key exists, return `Ok(new_dict)`
- if the key is missing, return `Err(MissingKey)`
- the returned `Result` is an ordinary runtime value
- do not mutate the original dict

## Error Model

Controlled collection failure:

```text
Err(MissingKey)
```

Runtime integrity failure:

```text
RuntimeError
```

Malformed runtime values and other boundary failures must raise controlled `RuntimeError`.

They must not be converted into `Err(MissingKey)`.

For all map operations requiring a key, malformed runtime key values outside the v1 supported set raise controlled `RuntimeError`.

They must not be converted into `Err(MissingKey)`.

## Architecture Boundaries

This phase explicitly forbids introducing:

- VM
- IR
- bytecode
- runtime parser
- runtime checker
- runtime inference
- collection framework
- `ExecutionContext`
- `CollectionExecutor`
- `IteratorFrame`
- `SequenceRuntime`
- `GenericApplyEngine`

Implementation, when it arrives, must remain direct and explicit.

## Future Tests

### `map.empty`

- empty map creation returns `{}` or the project’s canonical empty dict representation

### `map.get`

- valid key returns `Ok(value)`
- missing key returns `Err(MissingKey)`
- nested tuple value is preserved
- `RuntimeQuote` value is preserved
- stored `Ok(...)` value is preserved
- stored `Err(...)` value is preserved
- malformed map value raises controlled `RuntimeError`

### `map.contains`

- key present returns `true`
- key missing returns `false`
- nested values are preserved as ordinary runtime values
- malformed map value raises controlled `RuntimeError`

### `map.set`

- valid replacement returns new dict
- existing key is updated
- new key is inserted
- original dict remains unchanged
- nested tuple value is preserved
- `RuntimeQuote` value is preserved
- stored `Ok(...)` value is preserved
- stored `Err(...)` value is preserved
- malformed map value raises controlled `RuntimeError`

### `map.remove`

- existing key returns `Ok(new_dict)`
- missing key returns `Err(MissingKey)`
- original dict remains unchanged
- nested tuple values are preserved
- `RuntimeQuote` values are preserved
- stored `Ok(...)` values are preserved
- stored `Err(...)` values are preserved
- malformed map value raises controlled `RuntimeError`

### Map key restriction

Supported keys:

- Int key accepted
- String key accepted
- Bool key accepted

Acceptance is based on runtime value type only, not on the origin of the value.

Rejected keys:

- any runtime value whose runtime type is not Int, String, or Bool raises controlled `RuntimeError`

Examples:

- list values
- quotation values
- result values
