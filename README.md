# Nicole Python

This repository is the Python implementation of Nicole.

The language source of truth is the specification repository:
[hashtag1138/Nicole](https://github.com/hashtag1138/Nicole)

If code and spec diverge, the spec wins.

## Current target

NicolePy currently targets `v0.3.1-source-visible-host-abi-freeze`.

Target reference:

- spec repo: `/data/data/com.termux/files/home/Sources/nicole/nicole_language_docs_seed`
- tag: `v0.3.1-source-visible-host-abi-freeze`
- commit: `a8756807fc8bd8294d7fc44c146967ec270bedbf`

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
python -m pytest -q
```

## User compile/run facade (B6 freeze)

Recommended Python workflow for experimentation:

```python
from nicole.compiler import NicoleCompiler
from nicole.application import NicoleApplication
from nicole.diagnostic_renderer import render_diagnostic_error
from nicole.runtime import RuntimeHostBindings, RuntimeError, render_runtime_error
from nicole.errors import DiagnosticError

paths = [
    "examples/birthday_cli/main.nic",   # single file
    "samples/",                         # directory of .nic files
]

compiler = NicoleCompiler()
checked = compiler.compile(paths)       # file / directory / mixed list

app = NicoleApplication(
    paths,
    host_bindings=RuntimeHostBindings({
        "host.console.read": lambda: "Alice",
        "host.out.text": lambda text: None,
    }),
)

try:
    result = app.run("@app.main")       # explicit export name only
except DiagnosticError as error:
    print(render_diagnostic_error(error))
except RuntimeError as error:
    print(render_runtime_error(error))
else:
    print(result)
```

Facade constraints (intentional):

- no implicit entrypoint behavior
- no runtime session/debugger API in this facade
- no ABI migration in this layer (`HostContract`/`RuntimeHostBindings` stay legacy `host.*`)

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

## Host ABI source model

Nicole source now declares the source-visible host ABI explicitly with `module @host`.

Canonical source form:

```nicole
module @host
  opaque io.FileHandle
  require console.log { msg:String -- } dirty
  require io.open { -- out:@host.io.FileHandle } pure
end-module

module @app
  import @host.console.log as console.log
  import @host.io.{ open FileHandle } as io

  dirty : run { -- out:@host.io.FileHandle }
    "opening" console.log
    io.open
  ;

  export : run
end-module
```

Notes:

- source-visible host names are canonical `@host.*`
- host capabilities are declared by `require`
- host opaque types are declared by `opaque`
- grouped imports are expanded semantically to explicit imports
- `import @host.console.{ log read-line } as *` is explicit sugar, not a wildcard import
- direct source calls `host.*` are no longer valid Nicole source

Runtime value model:

- host opaque runtime values must still be wrapped as `RuntimeOpaqueValue(type_name=..., payload=...)`
- runtime matching remains nominal
- the Python payload type does not determine opaque identity

## Public surface notes

- User-defined words must be declared inside `module @name ... end-module`.
- Imports are top-level declarations.
- Exports are module-local declarations written as `export : word`.
- The canonical host-visible export name is `@module.word`.
- Import aliases do not affect host-visible export names.
- Legacy flat public syntax such as `export : app.run { ... }` is rejected.
- Source-visible host capabilities and opaque types are declared in `module @host`.
- Imported host capabilities remain callable symbols.
- Imported host opaque types are type-only symbols.
- `RuntimeOpaqueValue` is part of the public runtime surface for host opaque values.

## Runtime and ABI notes

- `run_export(checked, "@module.word", runtime_bindings, *args)` executes a checked export by canonical name.
- The runtime consumes `CheckedProgram` only and does not re-parse, re-resolve, or re-check source.
- `HostContract` and `ExportContract` remain the static host/export surfaces exposed by the Python implementation.
- The frontend is now canonical around `@host.*`, but `runtime.py` and `host_abi.py` still use a narrow legacy bridge based on `host.*`.
- Imported host capabilities resolve canonically, while runtime bindings are still keyed by legacy `host.*` names.
- The runtime host bridge identity split for imported host calls is:
- `resolution.qualified_name` is canonical `@host.*`.
- `resolution.host_binding_name` is legacy `host.*`.
- `IdentifierNode.name` preserves the source lexeme written in module code.
- For non-host symbols, `resolution.host_binding_name` remains `None`.
- This bridge metadata is internal migration state and is not a new public API contract.
- B5D freezes the Python ABI boundary explicitly:
- Nicole source/spec canonical host identities are `@host.*`.
- Python host ABI identifiers remain legacy `host.*`.
- runtime binding keys remain legacy `host.*`.
- runtime opaque type identities remain legacy `host.*`.
- no Python ABI migration is performed in B5D.
- `Quote<{ ... }>` and `DirtyQuote<{ ... }>` are not ABI-compatible in v1 and must not cross the host boundary.

## Current limitations

- Undeclared host opaque types are rejected in checker-visible type positions.
- `Map<@host.*, V>` and `Map<host.*, V>` remain forbidden. Opaque types may be map values only.
- Opaque values cannot be used with `=` or `!=`.
- Runtime host opaque values must use nominal `RuntimeOpaqueValue(type_name=..., payload=...)`.
- `Quote<{ ... }>` and `DirtyQuote<{ ... }>` remain forbidden across the ABI boundary.
- Runtime and host ABI alignment are intentionally split:
- source/spec host identity is canonical `@host.*`
- Python ABI/runtime host identity remains legacy `host.*`
- B5D freezes this boundary; adaptation/migration is deferred to a future phase.

## Additional docs

- Runtime quotations and `call`: [docs/runtime-quotations-call.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-quotations-call.md)
- Runtime collection core: [docs/runtime-collection-core-phase1.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-collection-core-phase1.md)
- Runtime list notes: [docs/runtime-list-phase2.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-list-phase2.md)
- Runtime map notes: [docs/runtime-map-core-phase1.md](/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation/docs/runtime-map-core-phase1.md)
