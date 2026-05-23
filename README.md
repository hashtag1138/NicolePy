# Nicole Python

This repository is the Python implementation of Nicole.

The language source of truth is the specification repository:
[hashtag1138/Nicole](https://github.com/hashtag1138/Nicole)

If code and spec diverge, the spec wins.

## Current target

NicolePy currently targets `v0.2.0-host-opaque-types`.

Target reference:

- spec repo: `/data/data/com.termux/files/home/Sources/nicole/nicole_language_docs_seed`
- tag: `v0.2.0-host-opaque-types`
- commit: `f125f675e2a4860323a778f77ba06f1cff17eb75`

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
python -m pytest -q
```

## Canonical usage

`from nicole.pipeline import analyze_program` is the canonical static entrypoint.
It performs parse -> signature collection -> standard builtin injection -> resolution -> checking -> export collection.

Example source:

```nicole
module @app
  : run { -- n:Int }
    42
  ;

  export : run
end-module
```

Static analysis:

```python
from nicole.pipeline import analyze_program

source = """
module @app
  : run { -- n:Int }
    42
  ;

  export : run
end-module
"""

checked = analyze_program(source)

print(checked.export_contract.words.keys())
```

Runtime execution:

```python
from nicole.runtime import RuntimeHostBindings, run_export

result = run_export(checked, "@app.run", RuntimeHostBindings({}))
print(result)
```

## Host opaque types

Host opaque types are declared by the host contract, not by Nicole source syntax.

Static declaration model:

- use `HostOpaqueType(name="host.io.FileHandle")`
- attach declarations to `HostContract`
- pass that contract into `analyze_program(...)`

Runtime value model:

- opaque values must be wrapped as `RuntimeOpaqueValue(type_name=..., payload=...)`
- runtime matching is nominal
- the `payload` Python type does not determine opaque identity

Canonical end-to-end flow:

```python
from nicole.host_abi import HostEffect, HostOpaqueType, HostWord, host_contract_from_words
from nicole.pipeline import analyze_program
from nicole.runtime import RuntimeHostBindings, RuntimeOpaqueValue, run_export

# `host_signature` is the HostWord signature for: { -- out:host.io.FileHandle }.
# It is provided by the host integration layer.
host_signature = ...

host_contract = host_contract_from_words(
    [HostWord(name="host.open", signature=host_signature, effect=HostEffect.PURE)],
    opaque_types=[HostOpaqueType(name="host.io.FileHandle")],
)

checked = analyze_program(
    """
module @app
  : run { -- out:host.io.FileHandle }
    host.open
  ;

  export : run
end-module
""",
    host_contract=host_contract,
)

handle = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload={"fd": 3})
runtime = RuntimeHostBindings({"host.open": lambda: handle})

result = run_export(checked, "@app.run", runtime)
print(result)
```

## Public surface notes

- User-defined words must be declared inside `module @name ... end-module`.
- Imports are top-level declarations.
- Exports are module-local declarations written as `export : word`.
- The canonical host-visible export name is `@module.word`.
- Import aliases do not affect host-visible export names.
- Legacy flat public syntax such as `export : app.run { ... }` is rejected.
- Host opaque types are declared through `HostContract.opaque_types`.
- `RuntimeOpaqueValue` is part of the public runtime surface for host opaque values.

## Runtime and ABI notes

- `run_export(checked, "@module.word", runtime_bindings, *args)` executes a checked export by canonical name.
- The runtime consumes `CheckedProgram` only and does not re-parse, re-resolve, or re-check source.
- `HostContract` and `ExportContract` are the static host/export surfaces exposed by the Python implementation.
- `Quote<{ ... }>` and `DirtyQuote<{ ... }>` are not ABI-compatible in v1 and must not cross the host boundary.

## Current limitations

- Undeclared `host.*` types are rejected in ABI-visible signatures and checker-visible type positions.
- `Map<host.*, V>` is forbidden. Opaque types may be map values only.
- Opaque values cannot be used with `=` or `!=`.
- Runtime host opaque values must use nominal `RuntimeOpaqueValue(type_name=..., payload=...)`.
- `Quote<{ ... }>` and `DirtyQuote<{ ... }>` remain forbidden across the ABI boundary.

## Additional docs

- Runtime quotations and `call`: [docs/runtime-quotations-call.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-quotations-call.md)
- Runtime collection core: [docs/runtime-collection-core-phase1.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-collection-core-phase1.md)
- Runtime list notes: [docs/runtime-list-phase2.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-list-phase2.md)
- Runtime map notes: [docs/runtime-map-core-phase1.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-map-core-phase1.md)
