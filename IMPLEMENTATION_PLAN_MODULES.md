# IMPLEMENTATION_PLAN_MODULES.md

## Plan maintenance rule

After each completed phase or audit:

- update phase status;
- append a Change log entry;
- record modified files;
- record validation results;
- record blockers;
- record residual gaps;
- record decisions taken during implementation.

This file is the authoritative implementation tracking document and must remain synchronized with repository state.

## Goal

Track implementation work for NicolePy to converge on the Nicole specification module/import/export model.

- Spec target tag: `v0.1.0-modules-freeze`
- Canonical ABI target: `@module.word`
- Legacy flat syntax (for example `export : app.run { -- n:Int } 0 ;`) is not supported public behavior.

## Baseline

- Implementation repository: `/data/data/com.termux/files/home/Sources/nicole/nicole_python_implementation`
- Baseline HEAD: `a0dc5a5eff740caa43ff8a1580cbb10ea3a22ad6`
- Baseline tag: `v0.17.0-case-guards-implementation`

## Source Of Truth

Nicole specification repository and tag:

- `/data/data/com.termux/files/home/Sources/nicole/nicole_language_docs_seed`
- `v0.1.0-modules-freeze`

---

## Phase 1A — Tokens, lexer, and AST

Status: `complete`

Goal:
- Introduce token/lexer/AST primitives for module/import/include/export declaration syntax and canonical qualified module references.

Allowed files:
- `src/nicole/tokens.py`
- `src/nicole/lexer.py`
- `src/nicole/ast_nodes.py`
- `tests/test_tokens.py`
- `tests/test_lexer.py`
- `tests/test_ast_nodes.py`

Forbidden files:
- `src/nicole/parser.py`
- `src/nicole/signature_collector.py`
- `src/nicole/resolver.py`
- `src/nicole/checker.py`
- `src/nicole/host_abi.py`
- `src/nicole/runtime.py`

Required behavior:
- Recognize module/import/include keywords and `@`-qualified module forms.
- Add AST nodes needed by module/import/include/export declarations.

Non-goals:
- No parser behavior change.
- No resolution/checker/runtime/ABI change.

Tests:
- Add/update tokenization and lexer tests for module/import/include and `@module.word`.
- Add/update AST structure tests for new declaration nodes.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_tokens.py tests/test_lexer.py tests/test_ast_nodes.py -q`

Exit criteria:
- New syntax primitives exist and related tests pass.

Notes:
- Keep changes frontend-only and avoid semantic assumptions.

Modified files:
- `src/nicole/tokens.py`
- `src/nicole/lexer.py`
- `src/nicole/ast_nodes.py`
- `tests/test_tokens.py`
- `tests/test_lexer.py`
- `tests/test_ast_nodes.py`

Validation results:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_tokens.py tests/test_lexer.py tests/test_ast_nodes.py -q`
- `65 passed`
- Phase 1A correction validation executed
- Phase 1A audit passed

Blockers:
- none

Residual gaps:
- Parser work still deferred to Phase 1B

---

## Phase 1B — Parser module syntax

Status: `complete`

Goal:
- Implement parser support for module/import/include/export declarations with strict public syntax aligned to spec.

Allowed files:
- `src/nicole/parser.py`
- `src/nicole/ast_nodes.py`
- `tests/test_parser.py`

Forbidden files:
- `src/nicole/signature_collector.py`
- `src/nicole/resolver.py`
- `src/nicole/checker.py`
- `src/nicole/host_abi.py`
- `src/nicole/runtime.py`

Required behavior:
- Parse `module @name ... end-module`.
- Parse import forms and include declarations.
- Parse `export : word` as declaration-only inside module.
- Reject top-level user word definitions.
- Reject dotted user word definitions and legacy export modifier forms as public syntax.

Non-goals:
- No symbol resolution semantics.
- No runtime/ABI behavior change.

Tests:
- Add parser positive tests for module/import/include/export declarations.
- Add parser negative tests for legacy flat forms and invalid placements.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_parser.py -q`

Exit criteria:
- Parser public surface reflects strict module syntax and rejects legacy public forms.

Notes:
- Any temporary compatibility aid must stay internal to tests and must not alter public parser behavior.

Modified files:
- `src/nicole/parser.py`
- `src/nicole/ast_nodes.py`
- `tests/test_parser.py`

Validation results:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_parser.py -q`
- `84 passed`
- Phase 1B audit passed

Blockers:
- none

Residual gaps:
- Import/alias semantics deferred to Phase 2
- Collision checks deferred to Phase 2
- Cycle checks deferred to Phase 2
- Checker/resolver/runtime/ABI integration unchanged

---

## Phase 1C — Syntax audit

Status: `complete`

Goal:
- Audit syntax implementation after Phase 1A/1B against spec requirements before symbol/resolution work.

Allowed files:
- Audit only; no edits expected.

Forbidden files:
- All source and test modifications during this phase.

Required behavior:
- Confirm token/lexer/AST/parser alignment with module/import/include/export declaration grammar.
- Confirm legacy flat export syntax is rejected publicly.

Non-goals:
- No resolver/checker/runtime/ABI implementation work.

Tests:
- Re-run syntax-focused tests to verify consistency.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_tokens.py tests/test_lexer.py tests/test_ast_nodes.py tests/test_parser.py -q`

Exit criteria:
- Syntax audit reports no blocking contradictions with `v0.1.0-modules-freeze`.

Notes:
- Record any mismatch as an explicit blocker before Phase 2.

Modified files:
- none

Validation results:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_tokens.py tests/test_lexer.py tests/test_ast_nodes.py tests/test_parser.py -q`
- `150 passed`
- Phase 1C correction validation executed
- Phase 1C audit passed

Blockers:
- none

Residual gaps:
- Qualified module atom syntax corrected; Phase 2 semantic work still deferred

---

## Phase 2A — Symbol model and signature collection

Status: `complete`

Goal:
- Introduce a module-aware symbol model and collect user words/import declarations from top-level declarations instead of flat top-level word assumptions.

Allowed files:
- `src/nicole/symbols.py`
- `src/nicole/signature_collector.py`
- `src/nicole/pipeline.py`
- `tests/test_signature_collector.py`

Forbidden files:
- `src/nicole/resolver.py`
- `src/nicole/checker.py`
- `src/nicole/runtime.py`
- `src/nicole/host_abi.py`
- `tests/test_resolver.py`
- `tests/test_checker.py`
- `tests/test_pipeline.py`

Required behavior:
- Collect user words from module declarations and module items.
- Preserve nested subword collection inside module-owned words.
- Represent module ownership explicitly in collected symbols.
- Capture top-level import and alias declarations for downstream resolution.
- Reject reserved-root module names and reserved-root import aliases.

Non-goals:
- No identifier resolution changes.
- No import graph cycle checks yet.
- No checker behavior changes.
- No ABI/runtime behavior changes.

Tests:
- Add/update collector tests for module-owned words, duplicate detection in-module, duplicate module declarations, reserved-root constraints, and import metadata capture.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_signature_collector.py -q`

Exit criteria:
- Collected symbol model is module-aware and no longer depends on flat top-level user-word collection as source of truth.

Risks:
- Symbol data model drift may break resolver/checker assumptions if not staged carefully.

Modified files:
- `src/nicole/symbols.py`
- `src/nicole/signature_collector.py`
- `tests/test_signature_collector.py`
- `IMPLEMENTATION_PLAN_MODULES.md`

Validation results:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_signature_collector.py -q`
- `18 passed`
- Phase 2A correction validation executed
- Phase 2A duplicate-scope correction validation executed
- Phase 2A audit passed

Blockers:
- none

Residual gaps:
- resolver semantics deferred to Phase 2B
- checker integration deferred to Phase 2C
- pipeline end-to-end integration deferred to Phase 2D
- with_standard_symbols() metadata preservation deferred to Phase 2D

---

## Phase 2B — Resolver imports and aliases

Status: `complete`

Goal:
- Implement module-aware resolution with import requirements, alias visibility, and reserved-root protections using currently available symbol metadata.

Allowed files:
- `src/nicole/symbols.py`
- `src/nicole/resolver.py`
- `tests/test_resolver.py`

Forbidden files:
- `src/nicole/signature_collector.py`
- `src/nicole/checker.py`
- `src/nicole/pipeline.py`
- `src/nicole/runtime.py`
- `src/nicole/host_abi.py`
- `tests/test_signature_collector.py`
- `tests/test_checker.py`
- `tests/test_pipeline.py`

Required behavior:
- Resolve same-module short names in module scope.
- Resolve `@module.word` only when allowed by current-module or matching import declaration.
- Resolve alias-qualified names only when alias is introduced by import.
- Reject unresolved external qualified references without required import.
- Enforce reserved-root protections for alias and visible-root collisions.
- Reject import cycles only when a complete import graph is available to the compiler.

Non-goals:
- No checker stack/effect semantics changes.
- No export ABI naming changes.
- No runtime behavior changes.

Tests:
- Add/update resolver tests for module-local short names, `@module.word`, alias-qualified references, missing imports, alias collisions, reserved-root violations, and conditional cycle rejection when complete import graph information is available.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_resolver.py -q`

Exit criteria:
- Resolver behavior matches module-aware import and alias rules without flat global-user-word fallback.

Risks:
- Resolver metadata changes may impact checker effect analysis and diagnostics.

Modified files:
- `src/nicole/symbols.py`
- `src/nicole/resolver.py`
- `tests/test_resolver.py`
- `IMPLEMENTATION_PLAN_MODULES.md`

Validation results:
- Implementation commit: `b19f06ebe55c3e54ccf2c623fc462231fc608392`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_resolver.py -q`
- `14 passed`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_signature_collector.py -q`
- `18 passed`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_parser.py tests/test_resolver.py tests/test_signature_collector.py -q`
- `117 passed`
- Phase 2B resolver/import/alias validation executed
- Phase 2B audit passed
- resolver.py deletion anomaly was a tooling artifact, not an actual deletion

Blockers:
- none

Residual gaps:
- Full import-graph cycle rejection is deferred until compilation-unit/module-loading assembly provides complete graph information.
- Visible-root collision diagnostics are limited to currently representable alias collisions in Phase 2B metadata.
- with_standard_symbols() metadata preservation remains deferred to Phase 2D.

---

## Phase 2C — Checker module integration

Status: `complete`

Goal:
- Adapt checker traversal and effect analysis to module-aware resolved symbols while preserving existing stack/type/effect rules.

Allowed files:
- `src/nicole/checker.py`
- `tests/test_checker.py`

Forbidden files:
- `src/nicole/symbols.py`
- `src/nicole/signature_collector.py`
- `src/nicole/resolver.py`
- `src/nicole/pipeline.py`
- `src/nicole/runtime.py`
- `src/nicole/host_abi.py`
- `tests/test_signature_collector.py`
- `tests/test_resolver.py`
- `tests/test_pipeline.py`

Required behavior:
- Consume module-aware resolution metadata without reintroducing flat naming assumptions.
- Keep local/builtin/host call checking behavior stable.
- Keep tail self-call marking and effect graph analysis correct under module-qualified ownership.

Non-goals:
- No new resolution rules.
- No pipeline orchestration changes.
- No ABI/runtime behavior changes.

Tests:
- Update checker fixtures to module-contained programs where needed.
- Preserve existing semantic assertions for type checking, control flow, effects, and tail-call marking.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_checker.py -q`

Exit criteria:
- Checker remains semantically stable with module-aware symbol ownership and resolver annotations.

Risks:
- Effect-analysis naming/ownership mismatches can cause subtle regressions in dirty-call and tail-call checks.

Modified files:
- `src/nicole/checker.py`
- `tests/test_checker.py`
- `IMPLEMENTATION_PLAN_MODULES.md`

Validation results:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_checker.py -q`
- `228 passed`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_resolver.py -q`
- `14 passed`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_signature_collector.py -q`
- `18 passed`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_parser.py tests/test_resolver.py tests/test_signature_collector.py tests/test_checker.py -q`
- `345 passed`
- Phase 2C checker/module-identity validation executed
- Phase 2C completed and ready for audit

Blockers:
- none

Residual gaps:
- `with_standard_symbols()` metadata preservation remains deferred to Phase 2D; checker tests that require import metadata avoid builtins augmentation until that deferred work is completed.

---

## Phase 2D — Pipeline integration and Phase 2 audit

Status: `pending`

Goal:
- Integrate Phase 2A/2B/2C behaviors in pipeline, migrate Phase 2 tests coherently, and complete Phase 2 module-aware audit readiness.

Allowed files:
- `src/nicole/pipeline.py`
- `src/nicole/symbols.py`
- `src/nicole/signature_collector.py`
- `src/nicole/resolver.py`
- `src/nicole/checker.py`
- `src/nicole/standard_symbols.py` (metadata preservation only during standard-symbol augmentation)
- `tests/test_signature_collector.py`
- `tests/test_resolver.py`
- `tests/test_checker.py`
- `tests/test_pipeline.py`

Forbidden files:
- `src/nicole/runtime.py`
- `src/nicole/host_abi.py`
- `tests/test_tokens.py`
- `tests/test_lexer.py`
- `tests/test_ast_nodes.py`
- `tests/test_parser.py`

Required behavior:
- Pipeline runs parser -> symbol collection -> standard symbols -> resolver -> checker with module-aware semantics.
- Preserve metadata through standard-symbol augmentation: `modules`, `imports`, `aliases`, and module ownership metadata.
- Correct the deferred integration defect: `with_standard_symbols()` currently rebuilds `SymbolTable` and preserves `words` only, dropping `modules`/`imports`/`aliases`.
- Phase 2 tests are green with module/import/alias/reserved-root/cycle behavior covered.
- No runtime/ABI functional changes introduced.

Non-goals:
- No canonical export ABI work (Phase 3).
- No runtime dispatch restructuring.
- No host ABI redesign.
- No unrelated builtin redesign outside metadata preservation needed for pipeline integration.

Tests:
- Update pipeline integration tests to module-aware fixtures.
- Ensure resolver/checker test updates are reflected in full Phase 2 validation.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_signature_collector.py tests/test_resolver.py tests/test_checker.py tests/test_pipeline.py -q`

Exit criteria:
- Phase 2A/2B/2C behavior is integrated and validated end-to-end without scope leak into Phase 3.

Risks:
- Integration-step domino effects across symbols/resolver/checker can surface late if prior phase boundaries were not strict.

Modified files:
- none

Validation results:
- none

Blockers:
- none

Residual gaps:
- none

---

## Phase 3 — Export declarations and canonical ABI

Status: `pending`

Goal:
- Implement export declaration semantics and canonical ABI publication using `@module.word`.

Allowed files:
- `src/nicole/signature_collector.py`
- `src/nicole/checker.py`
- `src/nicole/host_abi.py`
- `src/nicole/pipeline.py`
- `src/nicole/runtime.py`
- `tests/test_host_abi.py`
- `tests/test_pipeline.py`
- `tests/test_runtime.py`

Forbidden files:
- Broad runtime architecture rewrites outside export-name normalization and lookup alignment.

Required behavior:
- `export : word` binds only to existing same-module words.
- Export contract publishes canonical names only (`@module.word`).
- Duplicate canonical exports are rejected.
- Runtime export entry selection aligns to canonical names.

Non-goals:
- No public legacy alias support in final behavior.

Tests:
- Add/update ABI, pipeline, and runtime tests for canonical export naming and declaration semantics.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_host_abi.py tests/test_pipeline.py tests/test_runtime.py -q`

Exit criteria:
- Canonical export ABI behavior is implemented and covered by tests.

Notes:
- Runtime changes should remain minimal normalization only.

Modified files:
- none

Validation results:
- none

Blockers:
- none

Residual gaps:
- none

---

## Phase 4 — Legacy rejection, tests, docs, and SPEC_TARGET

Status: `pending`

Goal:
- Finalize public legacy rejection, complete test migration, update docs, and update `SPEC_TARGET.md` to modules-freeze target.

Allowed files:
- `README.md`
- `SPEC_TARGET.md`
- `docs/*`
- `tests/*`
- Any production files needed to remove temporary transitional scaffolding.

Forbidden files:
- Unrelated feature additions or refactors.

Required behavior:
- Legacy flat syntax is not documented or accepted as public behavior.
- Canonical ABI naming is documented as `@module.word`.
- Test suite reflects strict-spec module/import/export surface.

Non-goals:
- No new language features outside migration scope.

Tests:
- Rewrite/remove legacy flat-syntax tests.
- Add explicit rejection tests for top-level/dotted legacy forms.

Validation:
- `PYTHONPATH=src .venv/bin/python -m pytest -q`
- `grep -RIn "export : [A-Za-z0-9_-]*\\." README.md SPEC_TARGET.md docs tests src/nicole || true`

Exit criteria:
- Public docs/tests/spec-target metadata align with strict-spec behavior.

Notes:
- Transitional internal-only test scaffolding must be removed or disabled by phase end.

Modified files:
- none

Validation results:
- none

Blockers:
- none

Residual gaps:
- none

---

## Phase 5 — Final audit and release readiness

Status: `pending`

Goal:
- Perform final end-to-end audit against `v0.1.0-modules-freeze` and verify release readiness.

Allowed files:
- Audit only; no edits expected.

Forbidden files:
- No code/document modifications in this phase.

Required behavior:
- Verify parser/checker/resolver/runtime/ABI/docs/tests all align with target spec and strict compatibility decision.

Non-goals:
- No implementation additions.

Tests:
- Full suite and targeted grep audits for legacy patterns.

Validation:
- `git status --short`
- `PYTHONPATH=src .venv/bin/python -m pytest -q`
- `grep -RIn "\"app\\.run\"" README.md SPEC_TARGET.md docs tests src/nicole || true`

Exit criteria:
- Final audit reports release-ready state with no public legacy flat compatibility.

Notes:
- Any remaining gaps must be documented as explicit blockers.

Modified files:
- none

Validation results:
- none

Blockers:
- none

Residual gaps:
- none

---

## Current phase state

| Phase | Status |
|---|---|
| Phase 1A | complete |
| Phase 1B | complete |
| Phase 1C | complete |
| Phase 2A | complete |
| Phase 2B | complete |
| Phase 2C | complete |
| Phase 2D | pending |
| Phase 3 | pending |
| Phase 4 | pending |
| Phase 5 | pending |

---

## Change log

- Created plan from audit and strict-spec decision.
- Added plan maintenance rules.
- Added phase state tracking table.
- Added per-phase tracking sections.
- Phase 1A moved to in-progress with frontend-only token, lexer, and AST primitives plus focused test coverage.
- Corrected lexer handling for identifier grammar compatibility with spec.
- Phase 1A completed and passed audit.
- Consolidated duplicate Phase 1A tracking entries.
- Phase 1B moved to in-progress with module/import/include/export declaration parsing.
- Phase 1B completed and passed audit.
- Corrected expression-level qualified module syntax acceptance.
- Split Phase 2 into Phase 2A/2B/2C/2D for staged module-aware implementation.
- Phase 1C completed and passed audit.
- Phase 2A moved to in-progress with module-aware signature collection.
- Removed legacy program.words fallback from Phase 2A signature collection.
- Corrected Phase 2A duplicate detection from module-wide scope to owner scope.
- Phase 2A completed and passed audit.
- Corrected Phase 2B cycle scope: enforce cycle rejection only with complete import graph; defer full graph-cycle rejection until compilation-unit/module-loading assembly exists.
- Implemented Phase 2B module-aware resolver behavior for same-module, qualified import, and alias-based resolution paths.
- Phase 2B completed and passed audit with module-aware resolver/import/alias behavior.
- Phase 2C completed with checker-local module-aware identity for effect graph and tail-call analysis, plus checker test migration to module-contained fixtures.
- Corrected Phase 2D boundary to allow `src/nicole/standard_symbols.py` strictly for metadata preservation across standard-symbol augmentation (`modules`, `imports`, `aliases`, and module ownership metadata).
