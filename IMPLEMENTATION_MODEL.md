# IMPLEMENTATION_MODEL.md

This document defines the initial Python architecture for the Nicole implementation repository.
It is not normative.

The normative source is the Nicole specification repository:

- `https://github.com/hashtag1138/Nicole`
- `SYNTAXE.md`
- `SEMANTIQUE.md`
- `HOST_ABI.md`

The public examples are also useful consolidation material:

- `EXAMPLES.md`
- `INVALID_EXAMPLES.md`

If code and spec diverge, the spec wins.
Implementation follows specification, never the inverse.

Normative reference currently tracked:

- `2dfe20f59baac94aa331b439087d07e8db4430f3`

## Initial Pipeline

Canonical static pipeline:

1. `parse(source)`
2. `collect_signatures(program)`
3. `with_standard_symbols(symbols)`
4. `resolve(program, symbols, host_contract=...)`
5. `check(program, symbols)`
6. `collect_exports(symbols)`

Recommended entrypoint:

```python
from nicole.pipeline import analyze_program
```

`analyze_program(...)` returns a `CheckedProgram` containing:

- `program`
- `symbols`
- `host_contract`
- `export_contract`

Broader implementation priority remains:

1. Lexer
2. Parser
3. Signature collection
4. Name resolution
5. Type and stack effect checking
6. Simple IR
7. Interpreter
8. Host integration
9. Conformance tests

This order keeps syntax, naming, typing, execution, and host contracts separated.

## Internal Model

The live front-end and checker currently operate on the AST model in `src/nicole/ast_nodes.py`.

Canonical live structures include:

- `ProgramNode`
- `WordDefNode`
- `SignatureNode`
- `ParameterNode`
- `TypeNode`
- `QuoteTypeNode`
- `BlockNode`
- `IdentifierNode`
- `OperatorNode`
- `IfNode`
- `CaseNode`
- `CaseBranchNode`
- `QuoteNode`
- `HostWord`
- `ExportWord`
- `SymbolTable`

These are the structures that currently carry the parser, resolver, checker, and static ABI surface.

## Current Required Invariants

- one visible name designates one definition
- signature inputs are immutable locals, not an initial local stack
- local names must be unique inside one frame
- a word begins with an empty local stack
- reading a local pushes that local value onto the local stack
- `drop` acts on the local stack only
- quotations close with `;]`
- quotations execute in their own isolated frame
- quotation captures and quotation inputs belong to the same frame and must use distinct names
- bare `[]` is invalid; `[]:List<T>` is valid
- bare `map.empty` is invalid; `map.empty:Map<K,V>` is valid
- map keys are restricted in v1 to `Int`, `String`, and `Bool`
- `host.*` is reserved to the host
- a directly called `host.*` word is required in v1
- `pub` and `export` do not create separate namespaces
- v1 uses one compilation unit with no import graph or module graph
- `export` is top-level only
- a subword and a top-level word must not share one visible name
- `+`, `-`, `*`, `div`, and `mod` are `Int Int -> Int`
- `+.`, `-.`, `*.`, and `/.` are `Float Float -> Float`
- bare `/` is not a v1 arithmetic operator
- no implicit `Int`/`Float` coercion exists

Different frames may reuse the same local names.
Subwords never capture parent locals.
Quotations capture only explicitly through the stack at construction time.

## Error Model

Separate the following concerns:

- `StaticError`
- `RuntimeContractError`
- `IntegrationError`
- `DomainResult` for `Result<V,E>`

Do not model a missing `host.*` binding as a `Result`.
Binding absence is an integration problem, not a domain result.

Current `Result` rules to preserve:

- `Ok!` and `Err!` are constructors
- `Ok(v)` and `Err(e)` are `case` patterns
- `Ok(expr)` and `Err(expr)` are not v1 construction syntax
- `result.is-ok`, `result.is-err`, and `result.unwrap-or` are active v1 builtins
- `?` is active v1 syntax and is valid only in frames whose complete output is exactly one `Result<T,E>`

## Host ABI Model

Status note:

- a minimal static `HostContract` now exists
- a minimal static `ExportContract` now exists
- direct `host.*` calls require a known host contract during resolution
- host calls are checked through `SignatureNode`
- exported words are collected into a static ABI surface after successful analysis
- `export` must still not be documented as a complete runtime ABI registry
- `host_abi.py` should not be treated as the final runtime architecture
- ABI-compatible value families in v1 are `Int`, `Float`, `String`, `Bool`, `Unit`, `List<T>`, `Map<K,V>`, `Result<T,E>`, `ListError`, and `MapError`
- `Quote<{ ... }>` is forbidden across the ABI in v1

Track host contracts with explicit registries:

- export registry
- host registry
- required / optional availability
- binding failure
- runtime integration failure

The current public specification also distinguishes:

- static integration failure when a required direct `host.*` word is absent from the known contract
- runtime integration failure when a required binding cannot be satisfied dynamically
- future optionality from direct source-level calls in v1

Both `host.*` calls and exported program words follow the same language-level stack discipline.
The host must never observe the internal local stack of a word or quotation.

Implementation status that should not be overstated here:

- IR
- interpreter
- optional host fallback in direct source-level calls
- binding generation

Runtime support details should be checked against code and tests, not inferred from this architecture note alone.

Current stubs:

- `src/nicole/ir.py` is still a structural placeholder
- `src/nicole/interpreter.py` is still a placeholder
- the live checker is `src/nicole/checker.py`

## Current Type-Model Risk

The active implementation path now uses `TypeNode` / `SignatureNode` directly.

The removed legacy `types.py` / `signatures.py` model is no longer part of the live repository and must not be treated as an active design path.

## v1 Non-Goals

- no JIT
- no LLVM backend
- no complex async
- no threading model
- no advanced VM
- no optimization before conformity
- no final bytecode as the first target
