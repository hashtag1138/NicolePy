# NORMATIVE_SUMMARY.md

## Status

This document is not normative.
It is a working summary for the Nicole Python implementation.

The normative source is exclusively the Nicole specification repository:

- `https://github.com/hashtag1138/Nicole`
- `SYNTAXE.md`
- `SEMANTIQUE.md`
- `HOST_ABI.md`

The public examples are also useful consolidation material:

- `EXAMPLES.md`
- `INVALID_EXAMPLES.md`

Implementation follows specification, never the inverse.
If there is any conflict, the specification wins.

Revision of reference:

- `dadb99e9261827d63e7638deb67a10bf3406a09d`

## 1. Core Principles

- Nicole is a typed concatenative language.
- Word signatures are mandatory.
- Each word executes in an isolated frame.
- Signature inputs become immutable local variables.
- Word bodies manipulate a local stack.
- The implementation goal is correctness first, not optimization.

## 2. Word Structure

- A word is defined with `:` and terminated with `;`.
- The signature is always written as `{ inputs -- outputs }`.
- Input names create immutable local variables.
- Output names are documentary only and do not create variables.

Canonical example:

```sorte
: add { a:Int b:Int -- result:Int }
  a b +
;
```

## 3. Visibility and Host Boundary

- Without a modifier, a word is private to the current module.
- `pub` makes a word visible inside the program.
- `export` makes a word visible to the host and implies `pub`.
- `host.*` names words provided by the host.

Normative constraints:

- user code must not define `host.*`
- a visible name designates exactly one definition
- `pub` and `export` do not create distinct namespaces
- exported names must be unique
- two sibling subwords cannot share the same name
- a directly called `host.*` word is required in v1
- a required `host.*` word absent from the known host contract is a static integration error
- a required `host.*` binding failure is a runtime integration error
- optional host bindings do not justify direct source-level calls in v1

Invalid forms include:

- two top-level words with the same name
- two words with the same name but different input types
- two words with the same name but different arities
- a `pub` word and an `export` word with the same visible name
- two exports with the same name

Current repository status:

- the canonical static entrypoint is `nicole.pipeline.analyze_program(...)`
- it performs:
  - parse
  - user signature collection
  - standard builtin injection
  - resolution with `HostContract`
  - checking
  - export collection
- it returns a `CheckedProgram` carrying:
  - `program`
  - `symbols`
  - `host_contract`
  - `export_contract`
- `HostContract` is a minimal static host ABI contract
- `ExportContract` is a minimal static export ABI surface
- `pub` alone does not create an ABI export entry
- runtime host binding and runtime export linkage are still absent

## 4. Execution Model

Nicole distinguishes conceptually between:

- the caller stack
- the current word's local stack

On call:

1. arguments are taken from the caller stack
2. they become immutable local variables
3. the local stack starts empty
4. the body executes
5. declared outputs are pushed back onto the caller stack

Return constraints:

- missing value: error
- extra value: error
- incompatible type: error
- ignored values must be removed explicitly with `drop`

For Nicole-defined words, provable return violations must be rejected at compile time.

## 5. Local Variables

- Local variables are immutable.
- They are read-only.
- Reading them pushes their value onto the current local stack.
- They exist only inside the current word.
- They are not visible inside subwords.
- Local names must be unique inside one frame.

Frame rules:

- two inputs of the same word cannot share the same local name
- two quotation captures cannot share the same local name
- two quotation inputs cannot share the same local name
- a quotation capture and a quotation input cannot share the same local name
- different frames may reuse the same local name without ambiguity

Important consequence:

- signature inputs are not a preloaded local stack
- the local stack is empty at word entry
- `drop` at the beginning of a word is an underflow
- `x drop` reads `x`, pushes its value, then removes that pushed value

## 6. Subwords

- A word may contain subwords.
- Subwords are private by default.
- They are callable by short name from the parent.
- They are not public API in v1.
- There is no implicit lexical capture between parent and subword.
- In one parent scope, a subword name must be unique.
- A subword may reuse a local name that exists in the parent word because it executes in a different frame.

## 7. Static Resolution

Call resolution is static and uses the visible name in the relevant scope.

Constraints:

- one visible name maps to one definition
- collisions are compilation errors
- signature collection still happens before body analysis
- signature collection is needed for mutual recursion and early collision detection

## 8. Control Forms

### `if`

- `if` consumes a `Bool`
- the chosen branch executes in the same frame
- the `if` and `else` branches must produce the same stack effect

### `case`

- `case` consumes the value currently on top of the stack
- branches are tested in order
- `_` is the default pattern
- no guards exist in v1
- `when` does not exist in v1
- all branches must produce the same stack effect
- exhaustiveness must be checked statically when provable

Patterns retained for v1:

- `Int` literals
- `String` literals
- `Bool` literals
- `Ok(v)`
- `Err(e)`
- `MissingKey`
- `OutOfBounds`
- `_`

Binding rules:

- `Ok(v)` creates a branch-local binding `v`
- `Err(e)` creates a branch-local binding `e`
- `Err(MissingKey)` creates no binding
- `Err(OutOfBounds)` creates no binding
- `MissingKey`, `OutOfBounds`, and `_` create no binding

## 9. v1 Types

Types explicitly listed in the public specification and examples:

- `Int`
- `Float`
- `Bool`
- `String`
- `List<T>`
- `Map<K,V>`
- `ListError`
- `MapError`
- `Result<V,E>`
- `Quote<{ captures | inputs -- outputs }>`
- `Unit`

Important constraints:

- `{ -- }` means no output
- `{ -- u:Unit }` means a real `Unit` value
- `Unit` is not equivalent to absence of output

## 10. Stack Primitives and Basic Operations

Stack primitives:

- `dup`
- `drop`
- `swap`
- `over`
- `rot`

`drop` acts on the current local stack only.
It never removes a local binding.

Arithmetic and boolean operations include:

- `+`
- `-`
- `*`
- `+.`
- `-.`
- `*.`
- `/.`
- `div`
- `mod`
- `<`
- `<=`
- `>`
- `>=`
- `=`
- `!=`
- `and`
- `or`
- `not`

Current numeric rules:

- `+`, `-`, `*`, `div`, and `mod` are `Int Int -> Int`
- `+.`, `-.`, `*.`, and `/.` are `Float Float -> Float`
- bare `/` is not a v1 arithmetic operator
- there is no implicit `Int`/`Float` coercion
- `<`, `<=`, `>`, `>=` compare `Int Int` or `Float Float`, never mixed numeric kinds
- `=` and `!=` require exact type equality

## 11. Collections and Explicit Errors

### Lists

- Lists are immutable.
- bare `[]` is invalid in v1
- `[]:List<T>` is the explicit empty-list form
- `list.get` and `list.set` return a `Result<...,ListError>`
- `list.reduce` is only defined for non-empty lists

Canonical v1 operations:

- `list.len`
- `list.get`
- `list.set`
- `list.concat`
- `list.map`
- `list.fold`
- `list.reduce`

### `ListError`

v1 variants:

- `OutOfBounds`

### Maps

- `Map<K,V>` is immutable.
- bare `map.empty` is invalid in v1
- `map.empty:Map<K,V>` is the explicit empty-map form
- `map.get` returns `Result<V,MapError>`
- `map.set` and `map.remove` return a new map

v1 operations:

- `map.get`
- `map.contains`
- `map.set`
- `map.remove`
- `map.len`
- `map.keys`
- `map.values`

## 12. Lexical Minimum

- an identifier starts with an ASCII letter or `_`
- remaining identifier characters may include ASCII letters, digits, `_`, `-`, and `.`
- `-` may appear inside an identifier, but bare `-` remains an operator
- `.` participates in qualified names such as `host.log`
- strings use double quotes
- raw newline characters are not valid inside a string literal
- supported escapes include at least `\\\"`, `\\\\`, `\\n`, and `\\t`

## 13. Invalid Forms Now Explicit in the Public Spec

The current public specification now explicitly covers invalid cases such as:

- wrong closed `case` variants
- duplicate quotation captures
- duplicate quotation inputs
- duplicate quotation capture/input names inside one frame
- `list.reduce` on a provably empty list

### `MapError`

v1 variants:

- `MissingKey`

### `Result<V,E>`

`Result` represents normal and expected errors:

- `Ok(v)`
- `Err(e)`

`Result` does not model integration errors or runtime contract violations.

## 12. Quotations and `call`

Quotation form:

```sorte
:[ captures | inputs -- outputs | body ;]
```

Rules:

- value quotations are closed with `;]`
- closing with `]` alone is invalid
- captures are taken at quotation construction time
- inputs are consumed only at `call`
- quotation inputs become immutable locals
- quotation execution starts with an empty local stack
- a quotation executes in its own isolated frame
- captures and inputs share the same quotation frame and therefore must use distinct local names
- a quotation may explicitly capture a value under the same name as a local in the constructing word; this is explicit stack capture, not implicit lexical capture

Example:

```sorte
:[ | x:Int -- y:Int | x 1 + ;]
```

`call` must respect the quotation type exactly.

Higher-order builtin consequence:

- `list.map`, `list.fold`, and `list.reduce` consume an already constructed quotation value
- compatibility is checked on the callable part `inputs -- outputs`
- the quotation value may already include captures; these builtins do not require `captures == []`

## 13. Host Boundary

### `export`

- program word callable by the host
- unique export name
- explicit signature
- same return discipline as any Nicole word
- isolated frame
- host sees only declared outputs
- host does not see the local stack

### `host.*`

- `host.*` is part of the normative language boundary
- the Python repository does not yet claim a complete static host-contract checker or a complete ABI registry
- `export` and `host.*` should not be documented internally as already fully implemented ABI features

- host word callable by the program
- reserved namespace
- cannot be defined by user code
- explicit declared signature in the integration contract
- same stack discipline as any other call from the program side

## 14. Error Boundary

Reject statically when provable:

- syntax errors
- visible-name collisions
- invalid returns
- invalid `if` branch compatibility
- invalid `case` branch compatibility
- invalid quotation shape
- bare `[]`
- bare `map.empty`

Integration and runtime contract failures are distinct from language-level `Result`.
