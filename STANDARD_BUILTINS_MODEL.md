# STANDARD_BUILTINS_MODEL.md

## Status

Document non normatif.
Implementation model only.

Implementation follows specification, never the inverse.

This document models how Nicole Python should represent standard builtins and typed empty constructions.

## 1. What Standard Builtins Are

Some callable words exist in Nicole even when they are not defined by the user program.

Examples include:

- `result.is-ok`
- `result.is-err`
- `result.unwrap-or`
- `list.get`
- `list.set`
- `list.len`
- `list.map`
- `list.filter`
- `list.fold`
- `list.reduce`
- `list.concat`
- `map.get`
- `map.set`
- `map.contains`
- `map.remove`
- `map.len`

These words belong to the Nicole language.

They are not:

- user words
- `host.*` words
- runtime imports

## 2. Typed Empty Constructions Are Not Ordinary Naked Builtins

Nicole v1 also has two explicit empty constructions:

- `[]:List<T>`
- `map.empty:Map<K,V>`

Important current rules:

- bare `[]` is invalid
- bare `map.empty` is invalid
- `list.reduce` is only defined for non-empty lists
- the public invalid examples now include `list.reduce` on a provably empty list

Deferred, not active v1:

- `map.keys`
- `map.values`
- `map.items`
- `list.push`
- `list.pop`
- `list.contains`

Therefore `map.empty:Map<K,V>` must not be documented as an ordinary naked callable builtin equivalent to `map.get` or `list.len`.
It is a typed construction that must remain explicit in syntax and checking.

## 3. Builtins vs Host Words

Standard builtins and host words must remain distinct.

Standard builtin:

- `list.get`
- part of the language

Host word:

- `host.log`
- provided by the integration environment

The resolver and checker must distinguish:

- builtin language symbol
- host symbol
- user-defined symbol

`host.*` is an integration namespace, not a builtin namespace.

## 4. Where Builtins Enter the Pipeline

Expected pipeline:

```text
source
-> lexer
-> parser
-> AST
-> signature collection (user code)
-> standard builtin injection
-> resolver
-> checker
```

Canonical repository entrypoint:

```python
from nicole.pipeline import analyze_program
```

That façade performs builtin injection before resolution and checking.

Typed empty constructions are preserved by parsing and checked later.
They do not have to be injected as ordinary callable word symbols.

## 5. Representation Model

A standard callable builtin should be represented as a real symbol, not as a special string or parser shortcut.

It should carry enough metadata for:

- name
- stable identity
- visibility
- signature
- provenance

The provenance should make it possible to distinguish builtin symbols from user-defined symbols and host symbols.

Typed empty constructions may use a different internal representation because they are not ordinary naked calls.

## 6. Generic Builtins

Many builtins are polymorphic at the type level.

Examples:

```text
list.get { xs:List<T> index:Int -- Result<T,ListError> }
map.get  { m:Map<K,V> key:K -- Result<V,MapError> }
```

The resolver carries symbol identity forward.
Later checking stages handle compatibility and substitution.

For higher-order builtins:

```text
list.map    { xs:List<T> q:(Quote<{ | x:T -- y:U }> | DirtyQuote<{ | x:T -- y:U }>) -- ys:List<U> }
list.filter { xs:List<T> q:(Quote<{ | x:T -- keep:Bool }> | DirtyQuote<{ | x:T -- keep:Bool }>) -- ys:List<T> }
list.fold   { xs:List<T> init:Acc q:(Quote<{ | acc:Acc x:T -- out:Acc }> | DirtyQuote<{ | acc:Acc x:T -- out:Acc }>) -- out:Acc }
list.reduce { xs:List<T> q:(Quote<{ | a:T b:T -- c:T }> | DirtyQuote<{ | a:T b:T -- c:T }>) -- out:T }
```

The empty capture zone in these signatures means the builtin itself does not provide extra captures at call time.
It does not mean the quotation value must have been constructed without captures.
An already constructed quotation with captures remains valid if its callable part matches.
The builtins themselves are structurally pure; call-site effect depends on whether the quotation argument is `Quote` or `DirtyQuote`.
No distinct dirty builtin names exist (`dirty-map`, `dirty-filter`, `dirty-fold`, `dirty-reduce`).

Current result/error conventions tracked from the public specification:

- `list.get` returns `Result<T,ListError>`
- `list.set` returns `Result<List<T>,ListError>`
- `map.get` returns `Result<V,MapError>`
- `map.remove` returns `Result<Map<K,V>,MapError>`
- `OutOfBounds` belongs to `ListError`
- `MissingKey` belongs to `MapError`
- `Ok!` and `Err!` are constructors
- `Ok(v)` and `Err(e)` are `case` patterns, not construction syntax
- `result.is-ok`, `result.is-err`, and `result.unwrap-or` are active v1 builtins
- `?` is active v1 syntax and is valid only in frames whose complete output is exactly one `Result<T,E>`
- `Map<K,V>` key types are restricted in v1 to `Int`, `String`, and `Bool`

## 7. Visibility and Redefinition

User code must not redefine standard builtins.

For example:

```sorte
: list.get { ... } ;
```

must be rejected.

This rule keeps symbol identity stable and avoids collisions with language-provided names.

## 8. Consequences for `standard_symbols.py`

`standard_symbols.py` should provide the callable standard builtins explicitly.

It should:

- not parse source text
- not depend on source parsing
- construct builtin symbols directly

It should not model bare `map.empty` as a valid ordinary builtin call in Nicole v1.

## 9. Consequences for `signature_collector.py`

`signature_collector.py` must collect user code only.
It must also reject same-name collisions according to Nicole v1 visibility rules.

Standard builtins are injected after user signatures are collected.

## 10. Consequences for `resolver.py`

The resolver should receive:

- user symbols
- builtin symbols
- host symbols

and resolve them with explicit rules.

One visible name must designate one symbol.
The resolver should not describe several legal builtin alternatives for one source name.

## 11. Non-Goals

This model does not cover:

- runtime behavior
- host ABI execution
- VM lowering
- optimization
- interpreter internals

It only models symbol identity and typed-construction boundaries before type checking.
