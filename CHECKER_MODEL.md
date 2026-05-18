# CHECKER_MODEL.md

## Status

Document non normatif.
Implementation model only.

Implementation follows specification, never the inverse.

This document defines the checker architecture for Nicole Python.

## 1. Checker Boundary

The checker receives:

- resolved AST
- `SymbolTable`
- builtin symbols
- host symbol declarations when required by the integration contract

The checker produces:

- a validated program
  or
- type and stack-effect diagnostics

The checker verifies:

- type compatibility
- stack effects
- `if` branch consistency
- `case` branch consistency
- quotation compatibility with `call`
- standard builtin signature application
- host call stack-discipline consistency when a real `HostContract` is present

The checker does not perform:

- parsing
- name resolution
- builtin injection
- host runtime execution
- IR lowering
- interpretation

## 2. Type Stack Model

Nicole is concatenative and stack-based.

The checker uses a type-stack model:

```text
value stack
-> runtime

type stack
-> checker
```

Stack checking must remain structural and deterministic.

For a word body, the checker starts with an empty type stack.

Signature inputs are not preloaded onto the body stack.
They become immutable local variables.

Reading a local variable pushes its type onto the current type stack.

Example:

```sorte
: add { x:Int y:Int -- z:Int }
  x y +
;
```

starts as:

```text
locals = { x:Int, y:Int }
type_stack = []
```

then:

```text
x -> [Int]
y -> [Int, Int]
+ -> [Int]
```

`drop` at the beginning of a word with only signature inputs is a stack underflow, because inputs are locals, not pre-existing local-stack values.

`x drop` means:

1. read local `x`
2. push its value type onto the local stack
3. remove that stack value with `drop`

## 3. Type Checking vs Stack-Effect Checking

The checker groups two related but distinct responsibilities.

1. Type checking

- verifies that each consumed value has the expected type
- verifies word signatures
- verifies builtins
- verifies quotations
- verifies `case` patterns

2. Stack-effect checking

- verifies that each block transforms the stack as expected
- verifies that words return exactly the declared outputs
- verifies that `if` and `case` have compatible stack effects
- rejects missing or extra values

## 4. Identifier Validation

The resolver has already transformed source names into unique symbol identities.

The checker therefore works from:

```text
name -> unique resolved symbol
```

or an earlier resolution error.

The checker does not choose between several definitions.
Nicole v1 requires one visible name to map to one definition before checking.

## 5. `if`

Nicole form:

```sorte
condition if
  ...
else
  ...
end
```

The `Bool` consumed by `if` comes from the surrounding `BlockNode`, not from `IfNode` itself.

The checker must verify:

- the top of the type stack before `if` is `Bool`
- both branches have the same stack effect
- both branches leave the same output types in the same order

## 6. `case`

Nicole form:

```sorte
value case
  Ok(v) => ...
  Err(e) => ...
end
```

The checker verifies:

- the type of the scrutinee consumed from the current stack
- pattern compatibility with that scrutinee type
- exhaustiveness when the missing coverage is statically provable
- identical stack effect across all branches

Binding rules the checker must respect:

- `Ok(v)` introduces branch-local `v`
- `Err(e)` introduces branch-local `e`
- `Err(MissingKey)` introduces no local
- `Err(OutOfBounds)` introduces no local
- `MissingKey`, `OutOfBounds`, and `_` introduce no local

No guards exist in v1:

- `when` is invalid

## 7. Quotations

Quotation form:

```sorte
:[ captures | inputs -- outputs | body ;]
```

The checker must verify:

- captures are available at construction with compatible types
- quotation inputs are consumed only at `call`
- quotation inputs become immutable locals
- quotation execution begins with an empty local stack
- the quotation body matches the declared quotation signature
- `call` is used with a compatible quotation type
- local names inside one quotation frame must be unique across captures and inputs

Example:

```sorte
:[ | x:Int -- y:Int | x 1 + ;]
```

The quotation behaves like an anonymous word with its own isolated frame.

## 8. Builtins and Typed Empty Constructions

Standard callable builtins include:

- `list.len`
- `list.get`
- `list.set`
- `list.concat`
- `list.map`
- `list.fold`
- `list.reduce`
- `map.get`
- `map.contains`
- `map.set`
- `map.remove`
- `map.len`
- `map.keys`
- `map.values`

For higher-order list builtins:

- `list.map`, `list.fold`, and `list.reduce` consume an already constructed quotation value
- compatibility is checked on the callable part `inputs -- outputs`
- these builtins do not require the quotation to have `captures == []`

Current numeric rules tracked from the public specification:

- `+`, `-`, `*`, `div`, and `mod` are `Int Int -> Int`
- `+.`, `-.`, `*.`, and `/.` are `Float Float -> Float`
- bare `/` is not a v1 arithmetic operator
- `<`, `<=`, `>`, `>=` are valid on `Int Int` and `Float Float`
- `=` and `!=` require exact type equality
- no implicit `Int`/`Float` coercion exists

Important current v1 rules:

- bare `[]` is invalid
- `[]:List<T>` is valid
- bare `map.empty` is invalid
- `map.empty:Map<K,V>` is valid

The checker must therefore distinguish ordinary callable builtins from typed empty constructions.

## 9. Host Words and Exports

`host.*` remains distinct from builtins and user words.

Current public-spec host constraint:

- a directly called `host.*` word is required in v1
- if the known host contract lacks that word, this is a static integration error
- if the required binding fails dynamically, this is a runtime integration error
- optional presence testing and fallback are outside v1

The checker may verify, once the host contract exists:

- compatibility with the declared host signature
- that host calls follow the same stack discipline as other calls
- that exported words satisfy the same return discipline as any Nicole word

Current repository status:

- resolved `host.*` calls carry a `SignatureNode` from `HostContract`
- the checker applies that signature with the same input/output stack discipline as an ordinary call
- a missing host word is rejected before checking, during resolution
- a host word used with incompatible argument types is rejected by the checker
- `ExportContract` collection happens after successful checking; export ABI collection is not itself a checker responsibility
- this remains a minimal static ABI only, not a runtime integration model

It does not validate:

- runtime existence
- actual side effects
- host ABI execution behavior
- runtime export linkage
- binding generation

The host never sees the internal local stack of a word or quotation.

## 10. Error Model

A checking phase should define `CheckerError` or equivalent.

Typical examples:

- type mismatch
- insufficient stack
- incompatible branches
- invalid quotation body
- invalid builtin usage
- invalid host signature usage
- invalid typed empty construction usage

It must not reuse:

- `ParseError`
- `ResolutionError`
- runtime host failures

## 11. Consequences for `checker.py`

`checker.py` should:

- walk the resolved AST
- simulate the type stack
- validate exact return shapes
- validate branch compatibility
- validate quotations and `call`
- produce diagnostics

It should not pretend that a full host ABI checker already exists if the contract is still stubbed elsewhere.

It should not:

- parse
- resolve names
- execute the program
- build a VM
- perform lowering
