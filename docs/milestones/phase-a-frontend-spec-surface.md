# Phase A — Frontend Spec Surface

## Baseline

- spec target: `v0.3.1-source-visible-host-abi-freeze`
- NicolePy HEAD: `835e979e9450056d7e9c6c01787b8191d1d12839`
- date: `2026-05-27`
- status: `Phase A complete; Phase B through B4 implemented, with B4c/B4d pending commit`

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

## Etat reel post-B4

- Phase A is complete.
- Phase B1/B2/B3 are complete and committed.
- B4a and B4b1 are committed in `835e979e9450056d7e9c6c01787b8191d1d12839` (`feat: preserve canonical host identities`).
- B4c is implemented but not committed:
  - `birthday_cli/main.nic` now declares host ABI in `module @host`
  - `module @app` imports host capabilities from `@host`
  - the example no longer uses direct source `host.*`
  - the birthday example test no longer reconstructs host ABI signatures in Python
  - the birthday example test no longer rewrites Nicole source before execution
- B4d is implemented but not committed:
  - `README.md` is aligned to canonical `@host` source forms
  - `SPEC_TARGET.md` is aligned to `v0.3.1-source-visible-host-abi-freeze`

## Phase B completion summary

### B1

- semantic collection recognizes `module @host`, `require`, and `opaque`
- host ABI fragments consolidate into canonical `SourceHostContract`

### B2

- grouped imports are desugared into explicit internal imports
- grouped `as *` remains explicit sugar only, not wildcard semantics

### B3

- imported host symbols carry category metadata
- resolver rejects direct source `host.*`
- imported host opaque types are rejected in expression position
- imported host capabilities remain callable
- checker rejects host capability-as-type
- imported host opaque types are accepted in type position

### B4a

- parser preserves canonical `@host.*` in `TypeNode.name`
- checker accepts canonical host opaque types in type position
- legacy `host.*` fallback remains temporarily accepted

### B4b1

- resolver publishes canonical `ResolutionInfo.qualified_name` for imported host capabilities
- resolver keeps `ResolutionInfo.host_binding_name` as the legacy runtime bridge
- `IdentifierNode.name` still mutates to legacy `host.*` for runtime compatibility

### B4c

- `birthday_cli` is now source-driven for its host ABI
- the Nicole example file is the ABI source of truth
- the Python test only provides runtime bindings and assertions

### B4d

- public docs reflect canonical `@host` source syntax
- docs explicitly state that runtime and host ABI remain legacy-centric internally

## Historical Phase A patch breakdown

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
- status: `completed`

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
- status: `completed`

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
- status: `completed`

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
- status: `completed`

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
- status: `completed`

## Compatibilite Transitoire

- runtime remains keyed by legacy `host.*`
- `host_abi.py` remains legacy-centric
- `IdentifierNode.name` still mutates to legacy `host.*` for runtime execution
- `ResolutionInfo.host_binding_name` remains the explicit canonical-to-legacy bridge
- `tests/test_runtime.py` still carries a rewrite helper for remaining runtime-era fixtures
- B5 is the planned runtime/host ABI canonical alignment phase

## Regles de Validation

- audit before patch
- targeted tests after each patch
- full test suite before any eventual commit
- post-audit before commit
- no commit without explicit validation

## Remaining debt before B5

- runtime legacy
- host_abi legacy
- runtime bindings `host.*`
- `IdentifierNode.name` mutation to `host.*`
- runtime helper rewrite remaining in `tests/test_runtime.py`
- B5 futur
