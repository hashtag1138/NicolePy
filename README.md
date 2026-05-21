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

NicolePy currently targets `v0.16.0-self-tail-call`.

Current target reference:

- tag: `v0.16.0-self-tail-call`
- commit: `f2c6dfc5de817423c41f1f8060bdd1656b7b63a5`

Self-tail-call scope (v0.16):

- direct self-recursive calls in tail position are identified statically and optimized at runtime
- Nicole call-stack usage is constant for these marked direct self-tail-calls
- there is no syntax change for this feature
- no guarantee is provided for mutual recursion, indirect recursion, or recursion through quotations
- native/Python stack behavior remains outside the Nicole specification contract

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

Active execution architecture in the current migration baseline:

- source
- lexer
- parser
- signature collection + standard builtin injection
- resolver
- checker
- runtime AST execution (`run_export`)

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

Syntax and reserved-name note:

- canonical definition forms in the current baseline are `:`, `dirty :`, `pub :`, `pub dirty :`, `export :`, and `export dirty :`
- invalid modifier orders include `dirty pub :`, `dirty export :`, and `: dirty foo`
- exact `dirty` is reserved and invalid as a word name, subword name, local, capture, or output label
- names such as `dirty-int`, `dirty_log`, `is-dirty`, and `dirty.value` remain valid
- reserved namespaces remain `result.*`, `list.*`, `map.*`, and `host.*`

Effect note:

- Nicole is pure by default
- there is no `pure` keyword in v1
- `dirty` is explicit and checked exactly against inferred effect
- inferred pure + annotated dirty => error
- inferred dirty + missing dirty => error
- inferred dirty + annotated dirty => valid
- inferred pure + no annotation => valid
- only `host.*` bindings introduce impurity directly
- dirty propagation is transitive
- effect checking is static only
- there are no runtime dirty violations
- recursive and mutually recursive calls require SCC/fixed-point effect inference
- subwords may be dirty
- calling a dirty subword propagates dirty to the parent
- an unused dirty subword does not propagate dirty to the parent

Higher-order builtin note:

- `list.map`, `list.filter`, `list.fold`, and `list.reduce` consume an already constructed quotation value
- accepted quotation types are `Quote<{ ... }>` and `DirtyQuote<{ ... }>`
- compatibility is checked on the callable part `inputs -- outputs`
- a quotation passed to these builtins may already carry captures; they are part of the quotation value and are not supplied by the builtin itself
- higher-order builtins are structurally pure; call-site effect depends on whether the provided quotation is `Quote` or `DirtyQuote`
- there are no dirty-specific builtins such as `dirty-map`, `dirty-filter`, `dirty-fold`, or `dirty-reduce`

Quotation effect note:

- `Quote<{ captures | inputs -- outputs }>` is a pure quotation type
- `DirtyQuote<{ captures | inputs -- outputs }>` is a dirty quotation type
- a pure frame cannot construct, call, or pass a `DirtyQuote` to `list.map`, `list.filter`, `list.fold`, or `list.reduce`
- a dirty frame may construct, call, and pass `DirtyQuote`
- `call` on `Quote` is pure
- `call` on `DirtyQuote` is dirty

Result note:

- `Ok!` and `Err!` are the active v1 constructors
- `Ok(v)` and `Err(e)` are `case` patterns, not construction syntax
- `result.is-ok`, `result.is-err`, and `result.unwrap-or` are active v1 builtins
- `?` is active v1 syntax
- `?` is only valid in a frame whose complete output is exactly one `Result<T,E>`
- `Result`, `Err`, and `?` are orthogonal to dirty effects
- `Err` does not imply impurity
- `?` does not create dirty effect
- a dirty `host.*` word returning `Result<T,E>` remains dirty

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
- `export` implies `pub`
- `export` does not create dirty effect
- `export` preserves inferred effect
- a pure export cannot call dirty code
- a dirty export is valid only when its body is inferred dirty
- a required `host.*` word whose binding fails dynamically is a runtime integration error
- optional presence testing and fallback remain outside v1
- host contract effect metadata is mandatory (`effect: pure` or `effect: dirty`)
- there is no implicit default effect in host contracts
- required/optional availability is independent from effect
- directly called optional host bindings remain invalid in v1
- `dirty host.foo { ... }` is not Nicole source syntax
- ABI-compatible value families in v1 are `Int`, `Float`, `String`, `Bool`, `Unit`, `List<T>`, `Map<K,V>`, `Result<T,E>`, `ListError`, and `MapError`
- `Quote<{ ... }>` and `DirtyQuote<{ ... }>` are not ABI-compatible in v1 and must not cross the host boundary

Host contract examples:

```text
host.log
signature:
{ msg:String -- }
availability:
required
effect:
dirty
```

```text
host.timezone
signature:
{ -- tz:String }
availability:
required
effect:
pure
```

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
