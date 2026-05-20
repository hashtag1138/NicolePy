# RESOLVER_MODEL.md

## Status

This document is not normative.
It describes the internal resolver architecture for the Nicole Python implementation.

The normative source remains exclusively the Nicole specification repository:

- `https://github.com/hashtag1138/Nicole`
- `SYNTAXE.md`
- `SEMANTIQUE.md`
- `HOST_ABI.md`

The public examples are also useful consolidation material:

- `EXAMPLES.md`
- `INVALID_EXAMPLES.md`

Implementation follows specification, never the inverse.

## 1. Resolver Boundary

The resolver sits after:

- lexer
- parser
- signature collection

and before:

- type checking
- stack-effect checking
- IR lowering

Its input is:

- AST
- `SymbolTable`

Its output is:

- a resolved AST
- or an AST annotated with resolved symbols

The resolver's role is to turn unresolved textual references into explicit unique targets.

Example:

- source reference: `subtotal`
- resolved target: the single visible symbol `invoice.subtotal`

## 2. What Resolution Means in Nicole v1

Nicole v1 does not use same-name alternative definitions selected later by type.

Core invariant:

- one visible name designates one definition

Therefore the resolver must describe name lookup as:

```text
name -> one visible symbol
```

or else:

```text
name -> resolution error
```

Resolution errors include:

- unresolved name
- visible-name collision
- inaccessible private word
- invalid scope access

## 3. Responsibilities

The resolver is responsible for:

- resolving identifier references
- resolving naked word calls
- resolving subword access
- resolving lexical parent scope
- resolving the enclosing compilation-unit scope
- resolving visible `pub` words
- distinguishing Nicole-defined words from `host.*` words
- reporting resolution errors only

The resolver is not responsible for:

- type checking
- stack-effect checking
- host runtime validation
- ABI execution behavior
- execution semantics

## 4. Resolution Order

Lookup must be explicit and deterministic.

Expected order:

1. local bindings introduced by the current word or branch
2. nearest local subwords
3. lexical parent words when allowed
4. enclosing compilation-unit scope
5. visible `pub` words
6. visible `export` words as ordinary visible program words
7. `host.*` names reserved to the host namespace

The effective precedence must remain stable.
The current repository no longer accepts `host.*` purely by prefix.
A `host.*` reference is accepted only when the resolver receives a `HostContract`
containing that exact host word.

Nicole v1 has no import graph or module graph.
Resolution is over one compilation unit, not over multiple modules.

## 5. Collisions

Signature collection is still required before body analysis so mutually recursive words are known early.
It is also the natural place to detect collisions as soon as possible.

Invalid collision examples include:

- two top-level words of the same name
- two words of the same name with different input types
- two words of the same name with different arities
- two sibling subwords of the same name
- a subword and a top-level word with the same visible name
- a `pub` word and an `export` word with the same visible name
- two exports of the same name

The resolver must not treat these as alternative valid targets.
They are compilation errors.

## 6. Host Words

`host.*` names are not ordinary source-local identifiers.
They must resolve through the static `HostContract`.

The resolver must distinguish:

- Nicole-defined words
- host-provided words

Current repository behavior:

- if no `HostContract` is supplied, direct `host.*` references are rejected
- if a `HostContract` is supplied but lacks the referenced word, resolution fails
- if the host word exists in the contract, resolution records its `SignatureNode`
- runtime binding success remains outside the resolver boundary

Current public-spec constraint to preserve:

- a directly called `host.*` word is required in v1
- if the known host contract lacks that word, integration must fail
- optional host bindings do not make direct source-level `host.*` calls conditionally valid in v1

## 7. Export Visibility

`export` is visibility metadata plus host-facing identity.
It does not create a second namespace.

A word marked `export` is still a visible program word under the same naming discipline:

- same visible-name uniqueness rules
- same stack discipline
- same return discipline

The host-facing uniqueness rule must also be preserved:

- one export name designates one exported word

That rule is normative, and the current repository now materializes it as a minimal
static `ExportContract` collected after successful analysis.

## 8. Resolved Model

After resolution, an `IdentifierNode` is no longer just source text.
It is associated with:

- resolved symbol
- owner
- qualified name
- visibility
- signature reference

The resolved model must remain deterministic and inspectable for diagnostics.

## 9. Consequences for `resolver.py`

`resolver.py` should:

- walk the AST
- use `SymbolTable`
- annotate nodes with unique symbol identities
- return deterministic resolution results

It must not:

- produce several legal targets for one visible name
- guess from types
- simulate execution
- infer stack effects
- reinterpret syntax

## 10. Consequences for the Future Checker

The checker must consume resolved symbols, not raw unresolved strings.

That boundary is mandatory:

- parser produces syntax
- signature collection gathers visible declarations and detects collisions
- resolver binds names to unique symbols
- checker validates types and stack effects

The checker does not choose between several definitions because that is not a Nicole v1 feature.

Recommended high-level use is now:

```python
from nicole.pipeline import analyze_program
```

rather than reconstructing parse, signature collection, builtin injection, resolution,
checking, and export collection manually at each call site.
