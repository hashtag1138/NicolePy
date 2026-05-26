# Phase A — Frontend Spec Surface

## Baseline

- spec target: `v0.3.1-source-visible-host-abi-freeze`
- NicolePy HEAD: `83bf3d58ca28e0fcb04d0e8417d589e160fed9c6`
- date: `2026-05-26`
- status: `planned`

## Objectif

Represent correctly on the NicolePy frontend side the syntax surface required by the specification:

- `module @host`
- `require`
- `opaque`
- module-local imports
- grouped imports
- grouped `as *`
- canonical `@host.*` types

## Non-objectifs

- no runtime migration
- no removal of `host.*`
- no checker redesign
- no resolver redesign
- no deep ABI migration
- no spec modification

## Decoupage Patchs

### Patch A1 tokens/lexer

- scope:
  - add frontend token support for `require`, `opaque`, and `pure`
  - add lexer support required to represent grouped import prefixes and canonical `@host.*` type syntax
  - preserve current span behavior and current legacy tokenization where still required for compatibility
- files:
  - `src/nicole/tokens.py`
  - `src/nicole/lexer.py`
  - `tests/test_tokens.py`
  - `tests/test_lexer.py`
- tests:
  - keyword recognition for `require`, `opaque`, `pure`
  - grouped import prefix tokenization
  - canonical `@host.io.FileHandle` tokenization
  - legacy `host.*` tokenization non-regression
- risks:
  - breaking existing `QUALIFIED_MODULE_NAME` handling
  - introducing ambiguity between grouped imports and existing operator/generic parsing boundaries
  - accidental regression in token spans or EOF positions
- validation:
  - targeted `tests/test_tokens.py`
  - targeted `tests/test_lexer.py`
  - confirm no tracked diff outside this patch scope
- status: `pending`

### Patch A2 AST additive

- scope:
  - add AST structures required to represent `module @host`, `require`, `opaque`, and grouped imports
  - keep changes additive to avoid forcing immediate semantic/runtime migration
- files:
  - `src/nicole/ast_nodes.py`
  - `tests/test_ast_nodes.py`
- tests:
  - constructor coverage for new nodes and new additive fields
  - compatibility coverage for existing node creation paths
- risks:
  - changing dataclass signatures in ways that break downstream code
  - adding fields that are too semantic for a frontend-only phase
- validation:
  - targeted `tests/test_ast_nodes.py`
  - confirm existing parser-facing node assumptions still instantiate cleanly
- status: `pending`

### Patch A3 parser modules/import locality + `module @host` + `require`/`opaque`

- scope:
  - move import syntax acceptance from top-level to module-local placement
  - enforce import ordering within normal modules
  - parse `module @host` as a reserved frontend surface
  - parse `require` and `opaque` declarations in `module @host`
- files:
  - `src/nicole/parser.py`
  - `tests/test_parser.py`
  - `tests/test_diagnostics.py`
- tests:
  - valid module-local imports
  - invalid top-level imports
  - invalid imports after word definitions
  - valid `module @host` declarations
  - invalid non-host content inside `module @host`
  - parser diagnostics and spans for the new forms
- risks:
  - breaking many current parser tests that assume top-level imports
  - introducing parser-only rules that downstream semantic stages do not yet understand
- validation:
  - targeted `tests/test_parser.py`
  - targeted `tests/test_diagnostics.py`
  - confirm parser spans remain deterministic
- status: `pending`

### Patch A4 grouped imports + `as *` + `@host.*` en type

- scope:
  - parse grouped import syntax
  - parse grouped `as *` syntax as explicit grouped import surface, not wildcard semantics
  - parse canonical `@host.*` type forms
  - preserve temporary compatibility for legacy `host.*` type forms
- files:
  - `src/nicole/parser.py`
  - `tests/test_parser.py`
  - `tests/test_lexer.py`
- tests:
  - grouped import with alias prefix
  - grouped import with `as *`
  - invalid wildcard-like forms
  - canonical `@host.*` types in signatures
  - legacy type parsing non-regression where intentionally kept temporary
- risks:
  - ambiguity around grouped import delimiters
  - parser acceptance of syntax that checker/resolver still treat incorrectly
  - accidental silent widening into wildcard semantics
- validation:
  - targeted `tests/test_lexer.py`
  - targeted `tests/test_parser.py`
  - explicit invalid-form parser tests
- status: `pending`

### Patch A5 spans/diagnostics frontend

- scope:
  - finalize parser span coverage for new frontend forms
  - finalize parser diagnostic coverage for placement and syntax errors introduced by Phase A
  - keep renderer contract unchanged while extending parser diagnostics
- files:
  - `src/nicole/parser.py`
  - `tests/test_parser.py`
  - `tests/test_diagnostics.py`
- tests:
  - spans for `require`
  - spans for `opaque`
  - spans for grouped imports
  - diagnostics for invalid import placement
  - diagnostics for invalid `module @host` contents
- risks:
  - subtle line/column regressions
  - span boundary mistakes on grouped syntax and multi-token declarations
- validation:
  - targeted `tests/test_parser.py`
  - targeted `tests/test_diagnostics.py`
  - confirm no unintended lexer/test/runtime file changes
- status: `pending`

## Compatibilite Transitoire

- `host.*` remains temporarily accepted
- `host.*` runtime remains legacy
- `@host.*` will initially be frontend syntax only
- semantic enforcement is deferred to later phases

## Regles de Validation

- audit before patch
- targeted tests after each patch
- full test suite before any eventual commit
- post-audit before commit
- no commit without explicit validation
