# Nicole Python

This repository is the Python implementation of Nicole.

The normative specification lives in:
https://github.com/hashtag1138/Nicole

The authoritative files are:

- `SYNTAXE.md`
- `SEMANTIQUE.md`
- `HOST_ABI.md`

The public example files are also useful consolidation material for current v1 decisions:

- `EXAMPLES.md`
- `INVALID_EXAMPLES.md`

If code and spec diverge, the spec wins.

Implementation follows specification, never the inverse.

This repository is an implementation workspace, not a source of truth for the language.

Normative reference currently tracked by this repository:

- `2dfe20f59baac94aa331b439087d07e8db4430f3`

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

```python
from nicole.pipeline import analyze_program

source = """
export : main { -- n:Int }
  1
;
"""

checked = analyze_program(source)

print(checked.export_contract.words.keys())
```

The public spec still lives in [hashtag1138/Nicole](https://github.com/hashtag1138/Nicole).
NicolePy does not define the language.

Current documentation constraints:

- local names must be unique inside one frame
- different frames may reuse the same local names
- subwords never capture parent locals
- quotations capture only explicitly through the stack at construction time
- quotation captures and quotation inputs belong to the same frame and therefore must use distinct local names
- a subword may reuse a name that exists in the parent frame
- a quotation may explicitly capture a value under the same name as a local in the constructing word; this is explicit stack capture, not implicit lexical capture

Higher-order builtin note:

- `list.map`, `list.filter`, `list.fold`, and `list.reduce` consume an already constructed quotation value
- compatibility is checked on the callable part `inputs -- outputs`
- a quotation passed to these builtins may already carry captures; they are part of the quotation value and are not supplied by the builtin itself

Result note:

- `Ok!` and `Err!` are the active v1 constructors
- `Ok(v)` and `Err(e)` are `case` patterns, not construction syntax
- `result.is-ok`, `result.is-err`, and `result.unwrap-or` are active v1 builtins
- `?` is active v1 syntax
- `?` is only valid in a frame whose complete output is exactly one `Result<T,E>`

Host ABI note:

- `host.*` and `export` remain part of the language boundary defined by the spec
- the Python repository now exposes a minimal static ABI surface
- the canonical static entrypoint is `from nicole.pipeline import analyze_program`
- `analyze_program(source, *, host_contract=None)` performs:
  - parse
  - signature collection
  - standard builtin injection
  - resolution with `HostContract`
  - checking
  - export collection
- it returns a `CheckedProgram` carrying:
  - `program`
  - `symbols`
  - `host_contract`
  - `export_contract`
- `HostContract` exists as a minimal static host contract
- `ExportContract` exists as a minimal static export surface
- the Python repository does not define the language-level ABI beyond the current minimal static contracts documented here
- in v1, any directly called `host.*` word is required
- a direct `host.*` call without a supplied contract fails statically
- a required `host.*` word absent from the known host contract is a static integration error
- a host word present in the contract but used with incompatible types fails during checking
- `pub` alone does not create an ABI export entry
- `export` words do produce a static ABI entry
- export ABI names must be unique
- a required `host.*` word whose binding fails dynamically is a runtime integration error
- optional presence testing and fallback remain outside v1
- ABI-compatible value families in v1 are `Int`, `Float`, `String`, `Bool`, `Unit`, `List<T>`, `Map<K,V>`, `Result<T,E>`, `ListError`, and `MapError`
- `Quote<{ ... }>` is not ABI-compatible in v1 and must not cross the host boundary

Runtime ABI Phase 1:

- `RUNTIME_ABI_PHASE1.md` defines the current runtime bridge scope
- `run_export(checked, "app.run", runtime_bindings)` consumes a `CheckedProgram`
- the runtime executes the already checked AST directly
- it does not re-parse, re-resolve, or re-check
- `if`, `case`, runtime quotations, and `call` are documented in [docs/runtime-quotations-call.md](docs/runtime-quotations-call.md)
- runtime collection core Phase 1 is documented in [docs/runtime-collection-core-phase1.md](docs/runtime-collection-core-phase1.md)

Numeric note:

- `+`, `-`, `*`, `div`, and `mod` are `Int Int -> Int`
- `+.`, `-.`, `*.`, and `/.` are `Float Float -> Float`
- bare `/` is not a v1 arithmetic operator
- there is no implicit `Int`/`Float` coercion
- `<`, `<=`, `>`, and `>=` are same-kind ordered comparisons on `Int` and `Float`
- `=` and `!=` require exact type equality

Lexical note:

- an identifier starts with an ASCII letter or `_`
- later characters may include ASCII letters, digits, `_`, `-`, and `.`
- `-` may appear inside an identifier, but bare `-` remains an operator
- `.` is part of qualified names, not a standalone operator
- strings use double quotes, disallow raw newlines, and support at least `\\\"`, `\\\\`, `\\n`, and `\\t`

Compilation-unit note:

- Nicole v1 is analyzed as one compilation unit
- there is no import graph or module graph in v1
- `export` is top-level only
- a subword and a top-level word must not share one visible name

Builtin inventory note:

- active result builtins: `result.is-ok`, `result.is-err`, `result.unwrap-or`
- active list builtins: `list.len`, `list.get`, `list.set`, `list.concat`, `list.map`, `list.filter`, `list.fold`, `list.reduce`
- active map builtins/constructions: `map.empty:Map<K,V>`, `map.get`, `map.contains`, `map.set`, `map.remove`, `map.len`
- deferred, not active v1: `map.keys`, `map.values`, `map.items`, `list.push`, `list.pop`, `list.contains`

Map note:

- v1 map key types are restricted by the language to `Int`, `String`, and `Bool`
- `map.remove` returns `Result<Map<K,V>,MapError>`
