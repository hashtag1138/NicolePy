# Nicole Python

This repository is the Python implementation of Nicole.

The language source of truth is the specification repository:
[hashtag1138/Nicole](https://github.com/hashtag1138/Nicole)

If code and spec diverge, the spec wins.

## Current target

NicolePy currently targets `v0.1.0-modules-freeze`.

Target reference:

- spec repo: `/data/data/com.termux/files/home/Sources/nicole/nicole_language_docs_seed`
- tag: `v0.1.0-modules-freeze`
- commit: `08706edd315e64c22b47e69b4121a0f0f04e7a9f`

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

## Public surface notes

- User-defined words must be declared inside `module @name ... end-module`.
- Imports are top-level declarations.
- Exports are module-local declarations written as `export : word`.
- The canonical host-visible export name is `@module.word`.
- Import aliases do not affect host-visible export names.
- Legacy flat public syntax such as `export : app.run { ... }` is rejected.

## Runtime and ABI notes

- `run_export(checked, "@module.word", runtime_bindings, *args)` executes a checked export by canonical name.
- The runtime consumes `CheckedProgram` only and does not re-parse, re-resolve, or re-check source.
- `HostContract` and `ExportContract` are the static host/export surfaces exposed by the Python implementation.
- `Quote<{ ... }>` and `DirtyQuote<{ ... }>` are not ABI-compatible in v1 and must not cross the host boundary.

## Additional docs

- Runtime quotations and `call`: [docs/runtime-quotations-call.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-quotations-call.md)
- Runtime collection core: [docs/runtime-collection-core-phase1.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-collection-core-phase1.md)
- Runtime list notes: [docs/runtime-list-phase2.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-list-phase2.md)
- Runtime map notes: [docs/runtime-map-core-phase1.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-map-core-phase1.md)
