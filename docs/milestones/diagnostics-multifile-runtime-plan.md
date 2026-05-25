# NicolePy milestone — diagnostics, multi-file compilation, explicit runtime

## Initial audited baseline

- Initial audit date: 2026-05-23
- Initial audited HEAD: `9f7e3279b6c9a703a051dad345643b38b5b4b08c`
- Current tag(s): `v0.2.0-host-opaque-types`
- Audit source: previous Codex audit, "NicolePy Implementation Audit — Diagnostics, multi-file compilation, explicit runtime"
- Test baseline: 699 passed (audit baseline, HEAD 9f7e3279b6c9a703a051dad345643b38b5b4b08c)

## Goal summary

This milestone tracks a phased delivery for:

- source-aware diagnostics
- multi-file compilation
- explicit compiler API
- explicit interpreter API
- runtime diagnostics
- Nicole stack traces
- optional later host method binding

## Frozen phase list

0. Audit préalable
1. Source model
2. Tokens + AST spans
3. Structured compilation diagnostics
4. Multi-file compiler
5. Runtime diagnostics
6. Nicole stack trace
7. Interpreter API
8. User class API
9. Optional host method binding

## Dependency rule

- `SourceSpan -> AST -> diagnostics compilation -> diagnostics runtime`
- No rich diagnostic phase may start before file-bound range spans are stable.

## Architecture invariants

Source and diagnostics:

- lexer is the single origin of source provenance
- parser must never invent source locations
- source metadata flows forward only: lexer -> tokens -> AST -> symbols -> diagnostics/runtime
- diagnostics consume source metadata but do not own it
- source formatting concerns belong to diagnostic rendering, not source primitives
- no phase may recreate source provenance after lexing

Compiler and runtime separation:

- compiler owns source loading and static analysis
- interpreter owns execution
- runtime must consume `CheckedProgram`
- runtime diagnostics must not require recompilation
- multi-file compilation is a compiler concern only

Compatibility and migration:

- existing public APIs remain compatible during migration where possible
- migration layers should prefer wrappers/facades over duplicated logic
- runtime diagnostics must never expose opaque payload internals
- implementation phases should remain additive whenever possible

## Tracking rules

After every completed phase:

- record commit hash
- record test results
- record design decisions
- record deviations from the frozen plan
- record newly discovered risks
- update phase status
- append change log entry

## Decisions already taken

- Phase 1A is the first implementation patch.
- Multi-file compilation must be a compiler/loader feature, not an implementation of deferred include semantics.
- Existing public APIs must remain compatible where possible: `analyze_program(...)` and `run_export(...)`.
- `NicoleInterpreter` should wrap the existing `CheckedProgram` runtime model.
- Host method binding is deferred until after diagnostics and explicit compiler/interpreter APIs.
- Opaque runtime payloads must remain masked in diagnostics.

## Decision freeze before Phase 1A

Source model decisions:

- create a dedicated module `src/nicole/source.py`
- re-export `SourceSpan` from `src/nicole/tokens.py` for compatibility
- preserve historical construction `SourceSpan(line, column, offset)` during Phase 1A
- preserve compatibility accessors `span.line`, `span.column`, `span.offset`
- use end-exclusive ranges
- give EOF a zero-length span
- represent in-memory source as `<memory>`
- represent generic synthetic source as `<synthetic>`
- represent builtins source as `<builtin>`
- represent host-contract source as `<host-contract>`
- count columns as Python codepoints, matching the current lexer behavior
- do not put source excerpt or caret rendering helpers on `SourceSpan`; diagnostics formatting will own that later
- `SourceLocation` must be immutable
- `SourceSpan` must be immutable
- synthetic spans may have no physical file content

Phase 1A non-goals:

- do not change `Token.lexeme`
- do not change parser or AST behavior except imports required by the source model
- do not add rich diagnostics
- do not add multi-file compilation
- do not change `analyze_program(...)`
- do not change `run_export(...)`
- do not change runtime behavior

## Decision freeze before Phase 2

Phase 2 scope decisions:

- Phase 2 must cover all AST node families, not only executable nodes.
- Parser spans should use the earliest meaningful token as `start`.
- Parser spans should use the latest meaningful token end as `end`.
- Declaration spans should include the entire declaration.
- Module spans should include the full module declaration.
- Import spans should include the full import declaration.
- Export spans should include the full export declaration.
- Literal spans should include the entire literal token range.
- Quote and block spans should include delimiters when delimiters exist.
- Empty blocks should use a zero-length or delimiter-based span according to syntax availability.
- Synthetic, builtin and host symbols must use the source conventions frozen in Phase 1A.
- Phase 2 must not introduce rich diagnostics.
- Phase 2 must not change Nicole language semantics.
- Phase 2 must not change runtime behavior.
- AST nodes with synthesized origins must preserve explicit synthetic provenance

Program node:

- `ProgramNode` span starts at first declaration start.
- `ProgramNode` span ends at EOF zero-length span.
- Empty programs use EOF zero-length span.

Declarations:

- `ModuleDeclaration` spans include `module ... end-module`.
- `ImportDeclaration` spans include alias if present.
- `IncludeDeclaration` spans include path literals.
- `ExportDeclaration` spans include full declaration.
- `WordDefNode` start uses earliest meaningful modifier among `pub`, `dirty`, `:`.
- `WordDefNode` end uses terminating `;`.

Structured nodes:

- `SignatureNode` spans include delimiters.
- `QuoteTypeNode` spans include delimiters.
- `QuoteNode` spans include delimiters.
- `ListLiteralNode` spans include delimiters.
- `IfNode` spans include `if ... end`.
- `CaseNode` spans include `case ... end`.
- `TypedEmptyListNode` spans full `[]: Type`.
- `TypedEmptyMapNode` spans full `map.empty: Type`.

Parameters and types:

- `ParameterNode` ends at type end.
- `TypeNode` spans full type expression.
- Constructor patterns span through closing delimiter.
- `ParameterNode` starts at parameter name token and ends at parsed type end.
- `TypeNode` spans the entire parsed type expression.
- Generic type spans include closing generic delimiters.
- Quote-type arguments preserve full nested range provenance.

Blocks:

- `BlockNode` is container-derived.
- Non-empty blocks start at first contained token.
- Empty blocks use delimiter-based spans if available.
- Otherwise empty blocks use zero-length spans.

Case branches:

- `CaseBranchNode` starts at pattern start.
- `CaseBranchNode` ends at boundary token start.
- For a branch followed by another branch, boundary token is the next branch pattern start.
- For the final branch, boundary token is the enclosing `end` token.
- `CaseBranchNode` span must not require changes to `_parse_block` stop logic.
- `CaseBranchNode` span must not change supported pattern grammar.

Provenance:

- builtin symbols must use `<builtin>`
- host provenance behavior must be explicit
- synthetic AST nodes preserve synthetic provenance
- no node may silently downgrade provenance precision
- Case/pattern range propagation must not introduce nested or multi-argument constructor pattern support.
- Phase 2D must keep host provenance resolver/contract-owned.
- Phase 2D must not introduce host words into `SymbolTable`.
- Phase 2D must not introduce a host `SymbolSource`.
- `<host-contract>` remains a reserved source convention for later host diagnostics or host binding phases.
- Phase 2D implementation scope is builtin provenance plus explicit host deferral.

## Decision freeze before Phase 3A

Diagnostic model:

- `Diagnostic` is a data object, not a renderer.
- `Diagnostic.severity` is required.
- `Diagnostic.phase` is required.
- `Diagnostic.code` is required.
- `Diagnostic.message` is required.
- `Diagnostic.span` is optional.
- `Diagnostic.suggestion` is optional.
- `Diagnostic.notes` is optional and defaults to empty.
- `Diagnostic.cause` is optional.
- `SourceFile` is derived from `Diagnostic.span.source` when a span exists.
- Source excerpts and caret rendering are not stored on `Diagnostic`.

Severity and phase:

- Phase 3 starts with severity `ERROR`.
- `WARNING` and `NOTE` are reserved for later.
- Compile-time phases are `LEXER`, `PARSER`, `SYMBOLS`, `RESOLVER`, `CHECKER`, `ABI`, and `PIPELINE`.

DiagnosticError strategy:

- Introduce `DiagnosticError` as the common base for compile-time diagnostic exceptions.
- `DiagnosticError` carries `diagnostics: tuple[Diagnostic, ...]`.
- `DiagnosticError.diagnostic` exposes the first diagnostic.
- Phase 3 initially raises one diagnostic per exception.
- Existing public exception class names remain public.
- `LexError`, `ParseError`, `SymbolError`, `ResolutionError`, `CheckerError`, `HostABIError`, and `StandardSymbolError` become thin subclasses of `DiagnosticError`.
- Legacy `.message`, `.line`, and `.column` accessors are preserved where applicable.
- Early Phase 3 `__str__` remains legacy-compatible.

Compatibility:

- Structured diagnostics are additive first.
- Existing `pytest.raises(..., match=...)` behavior should mostly continue to pass.
- `analyze_program(...)` behavior remains compatible.
- Current exception identity is preserved.

Diagnostic codes:

- Codes use stable uppercase snake case.
- Codes are phase-prefixed.
- Examples:
  - `LEXER_UNTERMINATED_STRING`
  - `PARSER_EXPECTED_TOKEN`
  - `PARSER_DUPLICATE_PARAMETER_NAME`
  - `SYMBOLS_DUPLICATE_VISIBLE_NAME`
  - `RESOLVER_UNKNOWN_WORD`
  - `RESOLVER_UNKNOWN_HOST_WORD`
  - `CHECKER_TYPE_MISMATCH`
  - `CHECKER_CASE_NOT_EXHAUSTIVE`
  - `ABI_UNKNOWN_HOST_OPAQUE_TYPE`
- Codes must not encode source locations or formatting details.

Formatting and rendering:

- Diagnostics own data only.
- Renderer owns excerpts, carets, colors, note layout, and multi-line presentation.
- `source.py` must not gain diagnostic rendering helpers.
- Exception `__str__` is a compatibility layer, not the rich renderer.
- Rich excerpt/caret rendering is deferred to a later Phase 3 subphase.

Host ABI and source-less diagnostics:

- `Diagnostic.span=None` is valid.
- Phase 3 must not force synthetic `<host-contract>` spans onto current ABI errors.
- `<host-contract>` remains reserved for later host diagnostics or host binding phases.
- If an ABI/export error has a real Nicole source span, prefer that span.
- Otherwise use phase `ABI` with no span.

Pipeline behavior:

- `analyze_program(...)` continues to raise the first error only.
- Initial Phase 3 does not aggregate multiple diagnostics.
- Pipeline does not need to wrap phase-specific errors if they already subclass `DiagnosticError`.
- `PIPELINE` codes remain reserved for orchestration/wrapper failures.

Phase 3 subphases:

- `3A`: freeze diagnostic model, compatibility rules, code scheme, rendering ownership.
- `3B`: add `Diagnostic`, `DiagnosticError`, enums, compatibility accessors, legacy `__str__`.
- `3C`: adapt lexer and parser to structured diagnostics.
- `3D`: adapt symbol collection, resolver, and checker.
- `3E`: adapt host ABI and pipeline pass-through policy.
- `3F`: add renderer, source excerpts, and caret formatting.
- `3G`: finalize tests, tracking, and cleanup of remaining legacy-only assumptions.

Phase 3A non-goals:

- no runtime diagnostics
- no multi-file compiler
- no diagnostic aggregation
- no rich excerpt/caret renderer implementation
- no interpreter API
- no host method binding

## Allowed phase states

Possible phase states:

- pending
- in_progress
- completed
- blocked
- deferred
- abandoned

## Phase tracking table

| Phase | Status | Branch/commit | Summary | Tests | Notes |
|---|---|---|---|---|---|
| 0. Audit préalable | completed | `9f7e3279b6c9a703a051dad345643b38b5b4b08c` | Initial implementation audit completed and baseline captured | 699 passed | Audit-only step |
| 1. Source model | completed | `13e81bf865c1a9c86f32e47c350b1154fd6061aa` | Phase 1A completed: source primitives, compatible SourceSpan, lexer range spans | 707 passed | Committed and post-commit validated |
| 2. Tokens + AST spans | completed | `ca63c59fb5866e9da567f64b5f8824be50550c1f` | Phase 2 completed: AST spans and symbol provenance are range/source-aware | 750 passed | Completion audit passed; ready for Phase 3 diagnostics planning |
| 3. Structured compilation diagnostics | completed | `5c58008acebf324d35793a239e24bf748e462c1d` | Phase 3 completed: structured compilation diagnostics, ABI diagnostics, renderer, and cleanup finalized | 802 passed | Phase 3 completed; Phase 4 multi-file compiler pending |
| 4. Multi-file compiler | completed | `bb695b07afaf879b5ad9ec2dfb88988745a5102f` | Phase 4 completed: source-aware lexing, explicit file compile, recursive input normalization, and merged multi-file AST analysis are implemented | `13 passed`; `30 passed`; `821 passed` | Phase 4A and Phase 4E freezes integrated; Phase 5 runtime diagnostics is next |
| 5. Runtime diagnostics | completed | `7b4a14f2e60e7d3386403ef77d29d22a49b5a33c` | Phase 5 completed: runtime diagnostics architecture freeze, RuntimeDiagnostic foundation, raise-site conversion, context enrichment, and pure runtime diagnostic rendering are implemented | `218 passed`; `842 passed` | Global closeout result `PASS_PHASE5_READY_TO_CLOSE`; Phase 6A stack trace architecture audit is next |
| 6. Nicole stack trace | completed | `59166a394f9615a13dd2e0ddb7877ee2b3573708`; cleanup `2ebf6485e77cd84491dd526038fec1380505bede` | Phase 6 completed: runtime stack trace system is implemented and cleanup closeout is complete | `248 passed`; `872 passed` | Runtime stack trace system completed; immutable RuntimeStackTrace lifecycle implemented; RuntimeDiagnostic / RuntimeError trace attachment implemented; deterministic trace rendering implemented; RuntimeError.__str__ compatibility preserved; checker/runtime separation clarified and cleanup completed; renderer remains presentation-only; no semantic runtime changes introduced |
| 7. Interpreter API | completed | `6cf78848f7cdac9d24487783093366a0df4978d1` | Phase 7A implemented: `NicoleInterpreter` introduced, `run_export(...)` compatibility preserved, interpreter remains minimal, and `CheckedProgram` remains passive | PASS_READY_FOR_TRACKING | No runtime redesign introduced; no VM/session semantics introduced; package-root export decision deferred to Phase 8 |
| 8. User class API | completed | `484925f136bfab7145405deb133689987999482d` | Phase 8 closed: `NicoleApplication` validated as a thin orchestration facade with lazy compile, application-level `CheckedProgram` caching, and fresh `NicoleInterpreter` creation per run | `11 passed`; `888 passed`; `PASS_PHASE_READY_TO_CLOSE` | Layering preserved; runtime/checker separation preserved; no VM/session semantics, debugger/profiler/renderer semantics, host ABI inference, reflection-based behavior, or implicit entrypoint behavior introduced; package-root exports remain unchanged |
| 9. Tested examples corpus | in_progress | - | Phase 9 freeze recorded: a small, automatically tested corpus of realistic Nicole programs executed end-to-end through `NicoleApplication` is approved | `READY_FOR_PHASE9_FREEZE` | Frozen examples: `birthday_cli`, `file_report`, `http_status_checker`, `time_tracker`; `csv_contact_import` deferred; Phase 9 implementation is next |

## Audit findings summary

- Source model is now file-bound and range-based.
- Tokens carry file-bound end-exclusive spans.
- AST nodes are range-aware according to Phase 2 frozen conventions.
- Builtin symbols and builtin helper nodes use `<builtin>` provenance.
- Host provenance remains resolver/contract-owned and deferred.
- Lexer and parser now attach structured diagnostics (phase/code/span) while preserving legacy exception compatibility.
- Symbol collection, resolver, checker, and Host ABI now attach structured diagnostics; compile-time structured diagnostics are complete through Phase 3.
- Compile-time diagnostics now include structured payloads and renderer support while preserving legacy exception string compatibility; renderer support is complete.
- Remaining export-related `SymbolError` and `StandardSymbolError` legacy-only assumptions are now covered with explicit `SYMBOLS` codes and focused regression tests.
- Checker-internal `HostABIError` validation paths remain remapped to public `CheckerError` on checker entry points; user-visible checker behavior is unchanged.
- Renderer API decision for Phase 3 remains module-level import (`nicole.diagnostic_renderer`) with no package-level re-export.
- Multi-file compiler work is completed for Phase 4.
- `NicoleCompiler` now supports explicit files, explicit directories, and mixed iterables through normalized source discovery.
- Multi-file compilation now parses each source file independently, merges `ProgramNode` declarations in normalized order, rebuilds `ProgramNode.words`, and reuses the static analysis pipeline through `_analyze_program(...)`.
- `CheckedProgram.source_files` now exists as a backward-compatible field; `NicoleCompiler` fills physical source files while `analyze_program(...)` remains compatible with `source_files=()`.
- `PIPELINE_MULTIFILE_NOT_IMPLEMENTED` has been removed because merged AST reuse now implements multi-file compilation.
- Phase 7A introduced a minimal `NicoleInterpreter` API while preserving runtime semantics and compiler/runtime separation.
- Runtime raise sites now attach structured diagnostics for Phase 5.
- `RuntimeError` preserves legacy message behavior while carrying diagnostics.
- Runtime diagnostics preserve host cause chaining.
- Runtime diagnostics preserve opaque payload masking.
- Runtime behavior remains unchanged.
- Runtime stack traces remain deferred.
- Audit result: `PASS_ACCEPTED`.
- Direct diagnostic coverage added for `RUNTIME_INVALID_COMPARISON`.
- Direct diagnostic coverage added for `RUNTIME_INVALID_QUOTATION`.
- Direct diagnostic coverage added for `RUNTIME_UNSUPPORTED_OPERATION`.
- Direct diagnostic coverage added for representative `RUNTIME_RUNTIME_TYPE_ERROR`.
- Direct diagnostic coverage added for opaque payload masking assertions.
- Phase 5E implemented: pure runtime diagnostic renderer for `RuntimeDiagnostic` and `RuntimeError`.
- Runtime diagnostic rendering is deterministic and uses optional sections only.
- Runtime diagnostic rendering is mutation-free and ANSI-free.
- Runtime behavior remains unchanged after renderer introduction.
- Phase 5E audit result: `PASS_ACCEPTED`.
- Coverage added: minimal rendering, span rendering, operation rendering, notes rendering, cause rendering, RuntimeError rendering, deterministic rendering, no mutation, opaque masking.
- Phase 6A stack trace architecture audit completed with result `PASS_PHASE_READY_TO_CLOSE`.
- Runtime behavior currently preserved.
- No stack trace implementation exists yet.
- Current runtime architecture is compatible with future stack traces.
- No Nicole language semantic change required.
- No divergence detected with repository specification.
- Existing runtime diagnostics architecture can support future frame attachment.
- Documentation target references for the diagnostic phases are now aligned through Phase 3F planning.

## Compatibility constraints already observed

- Existing tests construct `SourceSpan(line, column, offset)` directly.
- Existing code and tests access `span.line`, `span.column`, and `span.offset`.
- Existing public API `analyze_program(...)` must remain compatible.
- Existing public API `run_export(...)` must remain compatible.
- Existing lexer behavior counts columns by Python string/codepoint progression.
- Runtime `Err(...)` payloads are not string-only in the current tested behavior, despite the current annotation.

### Phase 2 compatibility expectations

- Existing AST behavior should remain semantically identical.
- Existing parser behavior should remain semantically identical.
- Existing runtime behavior should remain unchanged.
- Existing public APIs should remain unchanged.
- Phase 2 changes should only improve source provenance precision.

## Decision freeze before Phase 4A

Phase 4 scope:

- multi-file compiler/loader only
- no include semantics
- no runtime diagnostics
- no Nicole stack trace
- no `NicoleInterpreter` API
- no user class API
- no host method binding

API direction:

- add `src/nicole/compiler.py`
- add `NicoleCompiler`
- add `compile_paths(inputs, *, host_contract=None)`
- preserve `analyze_program(source, *, host_contract=None)`
- preserve `run_export(...)`

Lexer direction:

- add `lex_source(source_file: SourceFile) -> list[Token]`
- preserve `lex(source: str)`
- preserve `Lexer.tokenize(source: str)`
- `lex(source)` must continue to use `SourceFile.memory(source)`

Loader decisions:

- accept files, directories, or mixed iterables
- compile only `.nic` files
- directory traversal is recursive
- ordering is deterministic by normalized path
- duplicate files are deduplicated by resolved path
- do not follow directory symlinks
- explicit wrong-extension file is an error
- missing file is an error
- directory with no `.nic` files is an error
- file-loading failures are structured diagnostics in `PIPELINE` phase

AST merge decisions:

- never concatenate source text
- parse each file independently
- merge `ProgramNode` declarations
- preserve each declaration's original `SourceSpan`
- do not combine spans across files

Include decision:

- `IncludeDeclaration` may continue to parse
- do not resolve include
- do not load include targets
- do not error merely because include exists

CheckedProgram direction:

- consider adding `source_files: tuple[SourceFile, ...] = ()`
- must remain backward compatible
- `NicoleCompiler` should expose real `source_files` when implemented

Phase 4 subphases:

- `4B`: source-aware lexer entrypoint
- `4C`: compiler skeleton for explicit files
- `4D`: recursive directory loader and input normalization
- `4E`: AST merge and full pipeline reuse
- `4F`: `CheckedProgram.source_files` provenance
- `4G`: final audit before code commit
- `4H`: tracking-only milestone update after code commit

Phase 4 invariants:

- parser never reads disk
- runtime never reads source files
- compiler owns loading
- existing single-source API remains compatible
- existing runtime API remains compatible
- diagnostics must retain physical file/line/column where applicable
- no source concatenation
- no language semantics changes in Phase 4

Phase 4 non-goals:

- no include semantics
- no runtime diagnostics
- no Nicole stack trace
- no `NicoleInterpreter` API
- no user class API
- no host method binding

## Decision freeze before Phase 4E

Phase 4E title:

- AST merge and full pipeline reuse

Audit result:

- previous proposed design was audited against real code
- result: `DESIGN_NEEDS_CORRECTION_BEFORE_IMPLEMENTATION`
- corrections are now frozen before implementation

Corrected Phase 4E decisions:

- parse each source file independently
- never concatenate source text
- merge top-level ASTs by constructing one merged `ProgramNode`
- merge `ProgramNode.declarations` in normalized file order
- rebuild `ProgramNode.words`; do not ignore it
- `ProgramNode.words` is real state
- `ProgramNode.words` must be rebuilt from all `WordDefNode` values contained in merged module declarations
- preserve original `SourceSpan` on declarations and nested nodes
- do not combine spans across files
- `ProgramNode.span` uses the parsed program span for single-file compile
- `ProgramNode.span` uses the first parsed program span for multi-file compile
- declaration and node spans remain authoritative for diagnostics
- no synthetic `<multifile>` source
- no cross-file physical span
- `IncludeDeclaration` remains inert: parse only
- `IncludeDeclaration` remains inert: no target loading
- `IncludeDeclaration` remains inert: no include resolution
- `IncludeDeclaration` remains inert: no error merely because include exists
- reuse the existing static analysis pipeline
- extract or add `_analyze_program(program, *, host_contract=None) -> CheckedProgram`
- remove or bypass `PIPELINE_MULTIFILE_NOT_IMPLEMENTED` only when merged AST analysis is implemented
- add backward-compatible `CheckedProgram.source_files: tuple[SourceFile, ...] = ()`
- `NicoleCompiler` fills `source_files` with the real physical `SourceFile` objects
- `analyze_program(...)` remains compatible and keeps `source_files=()`
- existing duplicate module behavior remains unchanged across files
- existing duplicate visible-name behavior remains unchanged across files
- existing duplicate export behavior remains unchanged across files
- no new module or import semantics in Phase 4E

Phase 4E non-goals:

- no runtime diagnostics
- no Nicole stack trace
- no `NicoleInterpreter` API
- no user class API
- no host method binding
- no include resolution
- no source concatenation
- no new language semantics

Phase 4E residual risks:

- `ProgramNode.span` for multi-file programs is only a representative span; declaration spans are authoritative
- `ProgramNode.words` rebuild is required and must be tested
- cross-file duplicates will surface existing diagnostics; this is intended

## Decision freeze before Phase 5A

Runtime diagnostic model:

- runtime diagnostics are structured data, not renderers
- existing public `nicole.runtime.RuntimeError` identity remains public
- `RuntimeError` becomes compatibility-wrapper plus diagnostic carrier
- runtime diagnostics are additive first
- existing runtime behavior should remain compatible where possible

RuntimeDiagnostic shape:

Required:

- severity
- phase
- code
- message

Optional:

- span
- operation
- suggestion
- notes
- cause

Forbidden in Phase 5:

- stack trace
- frame history
- locals snapshot
- runtime renderer ownership

Phase:

- add `RUNTIME`

Runtime codes:

- stable uppercase snake case
- `RUNTIME_STACK_UNDERFLOW`
- `RUNTIME_DIVISION_BY_ZERO`
- `RUNTIME_MISSING_EXPORT`
- `RUNTIME_CASE_MATCH_FAILURE`
- `RUNTIME_HOST_FAILURE`
- `RUNTIME_INVALID_QUOTATION`
- `RUNTIME_HOST_BINDING_MISSING`
- `RUNTIME_INVALID_COMPARISON`
- `RUNTIME_UNSUPPORTED_OPERATION`

Rules:

- codes must not encode source locations
- codes must not encode formatting

Span policy:

- runtime should use AST node spans when available
- no synthetic cross-file spans
- if no source exists: `span=None`

Opaque values:

- runtime diagnostics must never expose opaque payload internals

Host exception policy:

- runtime diagnostics may preserve Python exception chain internally
- user-visible diagnostics must not expose arbitrary host object internals

Tail-call constraints:

- self-tail-call optimization behavior remains unchanged
- runtime diagnostics must not create logical stack growth

Phase 5 subphases:

- `5B`: runtime diagnostic foundation
- `5B`: `RuntimeDiagnostic`
- `5B`: compatibility `RuntimeError`
- `5C`: convert runtime raise sites
- `5D`: runtime source/span attachment
- `5E`: host runtime failures
- `5F`: runtime cleanup and tests

Phase 5 non-goals:

- no Nicole stack traces
- no frame history
- no locals snapshots
- no `NicoleInterpreter` API
- no host method binding

## Decision freeze before Phase 5D

Phase 5D title:

- Runtime diagnostic context enrichment

Audit result:

- `RUNTIME_CONTEXT_READY_FOR_FREEZE`

Observed current state:

- `RuntimeDiagnostic` already has:
- `severity`
- `phase`
- `code`
- `message`
- `span`
- `operation`
- `suggestion`
- `notes`
- `cause`
- `RuntimeError` already exposes:
- `message`
- `diagnostic`
- `diagnostics`
- `RuntimeError` string behavior remains legacy-compatible
- Runtime raise sites already attach structured diagnostics after Phase 5C
- Runtime stack traces do not exist yet
- Runtime frame objects do not exist yet
- Locals snapshots do not exist yet

Phase 5D scope:

- enrich existing `RuntimeDiagnostic` payloads only where context is naturally available
- add or complete operation context where naturally available
- add or complete AST span context where naturally available
- add direct diagnostic assertions for previously under-tested categories:
- `RUNTIME_INVALID_COMPARISON`
- `RUNTIME_INVALID_QUOTATION`
- `RUNTIME_UNSUPPORTED_OPERATION`
- representative `RUNTIME_RUNTIME_TYPE_ERROR` paths
- preserve all existing runtime messages
- preserve all existing runtime behavior
- preserve host exception chaining
- preserve opaque payload masking
- preserve self-tail-call behavior

Phase 5D non-goals:

- no stack traces
- no frame objects
- no frame history
- no locals snapshots
- no runtime renderer
- no `NicoleInterpreter` API
- no host method binding
- no host binding redesign
- no new runtime semantics
- no message rewrites

Implementation constraints to record:

- spans must come only from existing AST nodes or existing natural runtime context
- if no natural span exists, use `span=None`
- do not synthesize source spans
- do not create cross-file spans
- operation must be a short stable string only when naturally known
- do not use operation as a substitute for future stack frames
- cause may be used only for real underlying exceptions or propagated runtime causes
- diagnostics must not expose `RuntimeOpaqueValue.payload`

Recommended Phase 5D implementation files:

- `src/nicole/runtime.py`
- `tests/test_runtime.py`

Files to avoid during implementation:

- `src/nicole/interpreter.py`
- `src/nicole/pipeline.py`
- `src/nicole/compiler.py`
- `src/nicole/checker.py`
- `src/nicole/host_abi.py`
- `src/nicole/parser.py`
- `docs/**` except tracking-only updates

Required test focus to record:

- invalid comparison diagnostic assertion
- invalid quotation diagnostic assertion
- unsupported operation diagnostic assertion
- representative runtime type error diagnostic assertion
- verify messages remain unchanged
- verify spans are natural or `None`
- verify no opaque payload appears in diagnostic message/notes
- verify runtime tests and full suite pass

Residual risks to record:

- `RuntimeDiagnostic.operation` must not become an implicit stack-frame model
- Phase 6 still owns stack trace design
- adding context across many runtime branches can accidentally change legacy messages if not tested carefully

## Decision freeze before Phase 5E

Phase title:

- Runtime diagnostic rendering

Audit result:

- `RUNTIME_RENDERING_READY_FOR_FREEZE`

Observed current state:

- `RuntimeDiagnostic` exists
- `RuntimeError` carries diagnostic(s)
- runtime diagnostics already have:
- `code`
- `message`
- `span`
- `operation`
- `notes`
- `cause`
- no runtime renderer exists
- no stack trace exists
- no frame objects exist
- diagnostics are currently raw objects only

Rendering responsibilities:

- transform `RuntimeDiagnostic` into readable output only
- preserve `RuntimeDiagnostic` as source of truth
- rendering layer must be pure presentation
- renderer must never modify diagnostics

Renderer output shape:

Required sections:

1.
Error header:

example:

`RuntimeError[RUNTIME_DIVIDE_BY_ZERO]`

2.
message

example:

`Division by zero.`

3.
location block if span exists:

example:

`file.nic:42:17`

4.
operation block if available:

example:

`Operation: divide`

5.
notes block if notes exist

6.
cause block if cause exists

Rules:

- absent fields produce no output section
- no empty placeholders
- no synthetic data generation
- preserve message exactly
- preserve code exactly

Phase 5E scope:

- add renderer only
- add renderer tests
- add formatting tests
- support `RuntimeDiagnostic` and `RuntimeError`

Phase 5E non-goals:

- no stack traces
- no frame model
- no locals snapshots
- no colored terminal output
- no ANSI formatting
- no rich library
- no IDE integration
- no interpreter API
- no logging framework
- no semantic runtime changes

Implementation constraints:

- renderer must be deterministic
- renderer must be side-effect free
- renderer must not mutate `RuntimeDiagnostic`
- renderer must not inspect `RuntimeOpaqueValue.payload`
- renderer must not synthesize spans
- renderer must not create frame information

Recommended future implementation files:

- `src/nicole/runtime.py`
- `tests/test_runtime.py`

Required future tests:

- render diagnostic with all fields
- render diagnostic without optional fields
- render `RuntimeError`
- verify exact message preservation
- verify deterministic output
- verify no payload leakage
- verify no mutation

Residual risks:

- rendering layout decisions may affect future stack-trace integration
- Phase 6 owns stack-frame design

## Decision freeze before Phase 6E

Phase 6E title:

- runtime trace rendering integration

Audit result:

- RUNTIME_TRACE_RENDERING_READY_FOR_FREEZE

Rendering order:

- render trace after operation
- render trace before notes and cause

Section order:

1. header/code
2. message
3. location
4. operation
5. trace
6. notes
7. cause

Trace section header:

- use `Stack trace:`

Frame rendering format:

- render frames as:
  `at <frame.name>`

Frame location rendering:

- if frame.span exists:
  append:
  ` (<file>:<line>:<column>)`
- if frame.span is absent:
  omit location entirely

Frame order:

- render outermost caller first
- render innermost failing frame last

Empty trace behavior:

- if trace is None:
  render nothing
- if trace exists but is empty:
  render nothing

Compatibility rules:

- diagnostics without trace must render exactly as before
- RuntimeError rendering without trace must render exactly as before
- RuntimeError.__str__ must remain unchanged

Non-goals:

- no ANSI formatting
- no colors
- no IDE integration
- no locals snapshots
- no frame history
- no JSON renderer
- no logging framework
- no semantic runtime changes
- no compiler/checker/parser changes

Renderer constraints:

- renderer remains deterministic
- renderer remains mutation-free
- renderer must not inspect RuntimeOpaqueValue.payload
- renderer must not mutate RuntimeDiagnostic
- renderer must not mutate RuntimeStackTrace

## Phase 6 closure summary

Completed:
- 6A architecture freeze
- 6B foundations
- 6C lifecycle
- 6D trace attachment
- 6E rendering integration
- 6F cleanup and final audit

Final audit result:

- PASS_PHASE_READY_TO_CLOSE

Closure verification:
- no stack execution redesign
- no locals snapshots
- no frame history
- no ANSI formatting
- no IDE integration
- no RuntimeError.__str__ drift
- no Nicole semantic changes

Residual accepted debt:
- runtime still contains defensive runtime validation overlap with checker
- remaining overlap is intentional defensive runtime policy, not primary semantic enforcement

## Decision freeze before Phase 7

Phase 7 title:

- Interpreter API

Audit result:

- INTERPRETER_API_READY_FOR_FREEZE

Primary goal:

- introduce explicit runtime/interpreter API
- preserve compiler/runtime separation
- preserve runtime semantics
- preserve compatibility

Frozen constructor:

- `NicoleInterpreter(checked: CheckedProgram, runtime_bindings: RuntimeHostBindings)`

Frozen execution entrypoint:

- `run_export(export_name: str, *args: object) -> object`

Compatibility rule:

- existing `run_export(...)` remains public
- existing `run_export(...)` becomes a thin facade over `NicoleInterpreter`

Ownership rules:

NicoleInterpreter owns only:
- CheckedProgram reference
- RuntimeHostBindings reference

Runtime-local only:
- RuntimeStack
- locals env
- RuntimeFrame
- RuntimeStackTrace
- RuntimeDiagnostic lifecycle
- execution-local state

CheckedProgram remains:
- passive compiled artifact only

Freeze decisions:

- no `CheckedProgram.create_interpreter(...)`
- no debugger API
- no stepping API
- no breakpoint API
- no renderer API
- no snapshot API
- no profiling API
- no logging API
- no reflection/inspection API
- no persistent VM/session semantics
- no coroutine/task semantics
- no runtime semantic redesign

Compiler/runtime separation:

Compiler owns:
- source loading
- parsing
- checking
- multi-file compilation
- compile-time diagnostics

Interpreter owns:
- execution entrypoint only

Runtime internals own:
- execution lifecycle
- stack
- trace lifecycle
- diagnostics
- host invocation
- tail-call behavior

Compatibility freeze:

- `analyze_program(...)` remains unchanged
- `NicoleCompiler` remains unchanged
- RuntimeError behavior remains unchanged
- Runtime stack trace behavior remains unchanged

Future extension boundary:

Future debugger/IDE/profiling systems must attach later as separate subsystems and must not be folded into NicoleInterpreter.

## Phase 7 non-goals

- no debugger subsystem
- no IDE subsystem
- no stepping
- no breakpoints
- no persistent runtime sessions
- no VM redesign
- no scheduler/task system
- no async redesign
- no runtime semantic changes
- no compiler redesign

## Next patch

Phase 7A

Name:

NicoleInterpreter minimal implementation

Scope:
- add NicoleInterpreter
- add minimal constructor
- add minimal run_export method
- preserve existing run_export compatibility facade
- preserve runtime semantics
- preserve compiler/runtime separation

Non-goals:
- no debugger
- no stepping
- no breakpoint support
- no renderer integration
- no profiler
- no reflection APIs
- no persistent runtime state

Tracking:
- implementation commit: `6cf78848f7cdac9d24487783093366a0df4978d1`
- Phase 7A implemented
- `NicoleInterpreter` introduced
- `run_export(...)` compatibility preserved
- interpreter remains minimal
- `CheckedProgram` remains passive
- no runtime redesign introduced
- no VM/session semantics introduced
- audit result: `PASS_READY_FOR_TRACKING`
- residual note: package-root export decision deferred to Phase 8

Phase 6 subphases:

6A:
stack trace architecture audit + freeze

6B:
RuntimeFrame and RuntimeStackTrace foundation implementation

6C:
frame lifecycle attachment

Scope:
- attach frames at frozen creation points
- preserve tail-call optimization behavior

6D:
RuntimeDiagnostic and RuntimeError trace attachment

Scope:
- attach RuntimeStackTrace to runtime diagnostics
- attach RuntimeStackTrace to RuntimeError as structured data
- preserve RuntimeError.__str__ compatibility
- preserve existing renderer behavior
- traces remain structured-only metadata

6E:
runtime trace rendering integration

Scope:
- render RuntimeStackTrace when present on RuntimeDiagnostic / RuntimeError
- preserve existing message/code/location/operation/notes/cause sections
- no ANSI
- no locals snapshots
- no frame history
- no IDE integration
- no semantic changes

Completion note:
- trace rendering now integrated into runtime diagnostics renderer

6F:
final audit, cleanup, closure

## Phase 1A detailed sequence

| Subphase | Action | Files likely touched | Exit criteria | Risk |
|---|---|---|---|---|
| 1A.1 | Audit all `SourceSpan` construction and accessor sites | `src/nicole/*.py`, `tests/*.py` | complete inventory of direct constructors, `.line/.column/.offset`, synthetic spans, token constructors | missed compatibility site |
| 1A.2 | Introduce compatible source primitives | `src/nicole/source.py`, `src/nicole/tokens.py`, focused tests | `SourceFile`, `SourceLocation`, `SourceSpan` exist; legacy constructor and accessors still work | import churn |
| 1A.3 | Make lexer emit range spans | `src/nicole/lexer.py`, span tests | all tokens, including EOF, carry file-bound end-exclusive range spans | off-by-one spans |
| 1A.4 | Add/adjust Phase 1A tests | `tests/test_tokens.py`, `tests/test_lexer.py`, optional `tests/test_source.py` | constructor, accessors, memory source, synthetic source, EOF, strings, multiline tokens covered | shallow coverage |
| 1A.5 | Post-phase audit and tracking update | milestone tracking file | tests recorded, commit hash recorded after commit, residual risks recorded | undocumented drift |

## Phase 2 detailed sequence

| Subphase | Action | Files likely touched | Exit criteria | Risk |
|---|---|---|---|---|
| 2A | Audit AST span propagation | `src/nicole/parser.py`, `src/nicole/ast_nodes.py`, `src/nicole/symbols.py`, tests | every AST node family mapped to a span convention | missed node family |
| 2B | Freeze AST span conventions | milestone tracking file | declaration, module, import, export, literal, quote and block conventions recorded | inconsistent conventions |
| 2C | Parser range propagation | `src/nicole/parser.py`, `src/nicole/ast_nodes.py` | AST nodes preserve or expand provenance precision without inventing new source origins | partial spans |
| 2D | Symbol provenance | `src/nicole/symbols.py`, `src/nicole/signature_collector.py`, `src/nicole/standard_symbols.py` | user, builtin, imported, host and synthetic symbols preserve explicit provenance categories | source-less diagnostics |
| 2E | Phase 2 tests | `tests/test_parser.py`, `tests/test_ast_nodes.py`, optional span tests | major syntax forms covered | shallow coverage |
| 2F | Post-phase audit and tracking update | milestone tracking file | tests, commit hash and residual risks recorded | undocumented drift |

## Phase 2 implementation notes

Phase 2 implementation constraints:

- parser must propagate provenance instead of recreating it
- parser should combine existing spans rather than synthesize new source locations
- parser must never replace a more precise span with a less precise span
- AST range upgrades must remain semantic no-ops
- symbol provenance must remain compatible with future diagnostics
- runtime behavior must remain unchanged
- no diagnostics formatting belongs in Phase 2

Known deferred work:

- checker synthetic helpers may still use synthetic spans
- host symbol provenance may remain resolver-owned until later phases
- host provenance remains resolver/contract-owned during Phase 2D
- first-class host provenance is deferred to diagnostics or host-binding phases
- runtime-generated helper nodes remain outside Phase 2 scope

## Phase 1A post-audit notes

- Phase 1A implementation passed post-audit.
- No fixes are required before commit.
- Provenance for real source tokens now originates in the lexer.
- Parser/AST span precision is intentionally deferred to Phase 2.
- Remaining synthetic provenance sites outside the lexer are pre-existing and deferred.
- `<builtin>` and `<host-contract>` conventions exist in the source model but are not fully wired into all producer sites yet.
- `SourceSpan` validation currently enforces monotonic offsets; stricter line/column consistency may be revisited later if needed.

## Phase 2B/2C.1 post-audit notes

- Phase 2B/2C.1 implementation passed post-audit.
- No fixes are required before commit.
- Parser span helpers combine existing spans instead of inventing source locations.
- Top-level declaration ranges are now propagated for `ProgramNode`, `ModuleDeclaration`, `ImportDeclaration`, `IncludeDeclaration`, `ExportDeclaration`, and `WordDefNode`.
- Parser semantics, runtime behavior and public APIs remain unchanged.
- Remaining Phase 2 nodes are intentionally deferred.
- Cross-source span guard is defensive and currently untested directly.
- Parser EOF fallback legacy behavior remains deferred.

## Phase 2B/2C.2 post-audit notes

- Phase 2B/2C.2 implementation passed post-audit.
- No fixes are required before commit.
- `SignatureNode`, `QuoteTypeNode`, `ListLiteralNode`, typed-empty-list path, and `QuoteNode` now include delimiter-aware ranges.
- Existing parser span helpers are reused; no new source locations are invented.
- Parser semantics, runtime behavior and public APIs remain unchanged.
- Block, control-flow, pattern and symbol provenance work remains deferred.
- Tests using delimiter occurrence indexes are acceptable for this patch but may become brittle if grammar token ordering changes.

## Phase 2B/2C.3 post-audit notes

- Phase 2B/2C.3 implementation passed post-audit.
- No fixes are required before commit.
- Non-empty `BlockNode` spans now start at the first contained node and end at the last contained node.
- Empty `BlockNode` spans use a zero-length span derived from the current boundary token.
- Empty-block boundary tokens may include `;`, `else`, `end`, `QUOTE_END`, or other enclosing syntax boundaries depending on parser context.
- No new source provenance is invented.
- Parser semantics, runtime behavior and public APIs remain unchanged.
- Control-flow, pattern and symbol provenance work remains deferred.

## Phase 2B/2C.4 post-audit notes

- Phase 2B/2C.4 implementation passed post-audit.
- No fixes are required before commit.
- `IfNode` spans now start at the `if` token and end at the terminating `end` token.
- Existing parser grammar is preserved: `else` remains required.
- Optional `else` support is explicitly out of scope and would require a separate syntax/semantics decision.
- Empty then/else block spans continue to use the Phase 2B/2C.3 `BlockNode` empty-boundary policy.
- Nested `if` ranges preserve inner and outer range boundaries.
- Parser semantics, runtime behavior and public APIs remain unchanged.
- `CaseNode`, `CaseBranchNode`, `PatternNode` and symbol provenance work remains deferred.

## Phase 2B/2C.5 post-audit notes

- Phase 2B/2C.5 implementation passed post-audit.
- No fixes are required before commit.
- `CaseNode` spans now include `case ... end`.
- `CaseBranchNode` spans now start at pattern start and end at boundary token start.
- Branch boundary behavior follows the frozen convention: next branch pattern start, or enclosing `end` for the final branch.
- Constructor `PatternNode` spans for `Ok(x)` and `Err(x)` now include the closing `)`.
- Pattern grammar is preserved: nested constructor patterns, multi-argument constructor patterns and arbitrary constructors remain rejected.
- Parser semantics, runtime behavior and public APIs remain unchanged.
- Symbol provenance work remains deferred.
- The branch boundary rule remains coupled to `_looks_like_case_branch_start_at_current()` and should be revisited only if case grammar changes.

## Phase 2D post-audit notes

- Phase 2D implementation passed post-audit.
- No fixes are required before commit.
- Builtin `WordSymbol`, `SignatureNode`, `ParameterNode`, `TypeNode`, and `QuoteTypeNode` helper spans now use `<builtin>` provenance.
- `SymbolSource.BUILTIN` behavior remains unchanged.
- Builtin names, signatures, effects and visibility remain unchanged.
- Host provenance remains resolver/contract-owned and deferred.
- `<host-contract>` is not used by builtins.
- Checker-local synthetic helper spans remain deferred.
- Parser semantics, resolver behavior, checker behavior, runtime behavior and public APIs remain unchanged.
- Builtin span positions remain conventionally zero-based at `(line=0, column=0, offset=0)`.

## Phase 2B/2C.6 post-audit notes

- Phase 2B/2C.6 implementation passed post-audit.
- No fixes are required before commit.
- `ParameterNode` now starts at parameter name token and ends at parsed type end.
- Plain `TypeNode` remains token-range only.
- Generic `TypeNode`, `Quote` and `DirtyQuote` wrappers now include closing `>`.
- Nested quote-type provenance remains full-range.
- `TypedEmptyListNode` now spans full `[]: Type`.
- `TypedEmptyMapNode` now spans full `map.empty: Type`.
- Parser grammar and malformed type behavior remain unchanged.
- Parser semantics, runtime behavior and public APIs remain unchanged.

## Phase 2 completion notes

- Phase 2 completion audit passed after final parser span patch.
- Phase 2 is functionally complete in code.
- Parser AST spans now follow the frozen Phase 2 range conventions.
- Builtin provenance now uses `<builtin>` spans.
- Host provenance remains explicitly deferred.
- Checker-local synthetic spans remain deferred.
- No diagnostics, runtime, compiler, interpreter or language semantic changes were introduced.
- Phase 3 may start only after this tracking cleanup is committed.

## Phase 4B post-audit notes

- Phase 4B implementation passed post-audit.
- No fixes are required after validation.
- `lex_source(source_file: SourceFile) -> list[Token]` was added.
- `Lexer.tokenize_source(source_file: SourceFile)` was added.
- `lex(source: str)` remains compatible and continues to use `SourceFile.memory(source)`.
- `Lexer.tokenize(source: str)` remains compatible.
- Token spans and lexer diagnostics from `lex_source(...)` now preserve the provided physical `SourceFile`.
- Parser behavior, runtime behavior, diagnostics model, token kinds, lexeme behavior, column counting, and EOF behavior remain unchanged apart from preserving the provided source file.
- Phase 4C compiler skeleton work is next.

## Phase 4C post-audit notes

- Phase 4C implementation passed post-audit.
- No fixes are required after validation.
- `src/nicole/compiler.py` was added.
- `NicoleCompiler` was added.
- `NicoleCompiler.compile(input_path)` was added.
- `NicoleCompiler.compile_file(file_path)` was added.
- `compile_path(input_path, *, host_contract=None)` was added.
- Explicit file-only compilation now flows through physical `SourceFile` instances.
- Structured `PIPELINE_*` diagnostics were added for directory input not supported yet, missing files, and unsupported explicit file extensions.
- `analyze_program(...)` remains compatible.
- Parser behavior, language semantics, runtime behavior, diagnostic structure, and exception identities remain unchanged.
- Phase 4D recursive directory loader and input normalization work is next.

## Phase 4D post-audit notes

- Phase 4D implementation passed post-commit audit with result `PASS_READY_FOR_TRACKING`.
- No fixes are required before tracking update.
- `NicoleCompiler.compile(...)` now accepts `str | Path | Iterable[str | Path]`.
- Recursive directory discovery for `*.nic` inputs was added.
- Input ordering is deterministic by resolved path.
- Duplicate inputs are deduplicated by `Path.resolve()`.
- Symlink-directory traversal is blocked.
- Symlinked `.nic` files are accepted by the implementation/design.
- Structured `PIPELINE_*` diagnostics cover missing source, unsupported explicit extension, and empty source set.
- A temporary `PIPELINE_MULTIFILE_NOT_IMPLEMENTED` gate now blocks multiple discovered files until later Phase 4 semantic merge work.
- Phase 4D intentionally did not add AST merge, source concatenation, include semantics, `CheckedProgram.source_files`, runtime diagnostics, interpreter API, user class API, or host method binding.
- `analyze_program(...)` remains compatible.
- Residual risk: symlinked `.nic` file acceptance is implemented by design but is not yet directly tested.
- Phase 4E AST merge and full pipeline reuse work is next.

## Phase 4E pre-implementation audit notes

- Previous proposed Phase 4E design was audited against the real repository.
- Audit result: `DESIGN_NEEDS_CORRECTION_BEFORE_IMPLEMENTATION`.
- The corrected Phase 4E decisions are now frozen before implementation.
- `ProgramNode.words` rebuild is mandatory and must not be omitted.
- Multi-file `ProgramNode.span` must remain a representative single-file span; declaration spans remain authoritative.
- `CheckedProgram.source_files` remains planned as backward-compatible `tuple[SourceFile, ...] = ()`.
- `analyze_program(...)` remains compatible and should keep `source_files=()`.
- Cross-file duplicate module, duplicate visible-name, and duplicate export behavior should continue using current diagnostics.
- Phase 4E implementation is next.

## Phase 4E post-audit notes

- Phase 4E implementation passed accepted validation and is complete.
- No fixes are required before tracking update.
- Each source file is now parsed independently before merge.
- Multi-file compilation now constructs one merged `ProgramNode` without source concatenation.
- Merged declarations preserve normalized file order.
- `ProgramNode.words` is rebuilt from merged module declarations.
- Original declaration and nested node provenance is preserved.
- Multi-file `ProgramNode.span` remains representative only; declaration spans remain authoritative for diagnostics.
- `_analyze_program(program, *, host_contract=None)` was introduced to reuse the existing pipeline.
- `CheckedProgram.source_files` was added as backward-compatible `tuple[SourceFile, ...] = ()`.
- `NicoleCompiler` retains physical source files on compiled programs.
- `analyze_program(...)` remains backward compatible and keeps `source_files=()`.
- Include declarations remain inert.
- Duplicate module, duplicate visible-name, and duplicate export behavior remains unchanged.
- `PIPELINE_MULTIFILE_NOT_IMPLEMENTED` was removed because merged AST reuse now supports multi-file compilation.
- Phase 5 runtime diagnostics work is next.

## Phase 5A audit notes

Result:

- `RUNTIME_READY_FOR_DESIGN_FREEZE`

Observed:

- runtime currently lacks frame objects
- runtime currently lacks stack traces
- runtime currently uses message-only `RuntimeError`
- `CheckedProgram.source_files` exists but runtime does not consume it
- self-tail-call optimization already exists

Risks:

- future frame design
- tail-call interaction
- opaque payload exposure
- host exception exposure
- runtime-generated synthetic nodes

## Phase 5B post-audit notes

Result:

- `PASS_READY_FOR_TRACKING`

Notes:

- runtime diagnostic foundation exists
- runtime raise sites still use legacy messages
- runtime diagnostic conversion remains deferred to Phase 5C
- runtime stack model remains unchanged
- runtime frame model remains deferred to Phase 6

## Phase 5C post-audit notes

- Phase 5C implementation passed post-audit
- Result: `PASS_READY_FOR_TRACKING`
- Runtime behavior unchanged
- Tail-call behavior unchanged
- No synthetic spans introduced
- No opaque payload exposure detected
- Existing `RuntimeError` compatibility preserved
- Residual test coverage gap only:
- direct diagnostic assertions still missing for `RUNTIME_INVALID_COMPARISON`
- direct diagnostic assertions still missing for `RUNTIME_INVALID_QUOTATION`
- direct diagnostic assertions still missing for `RUNTIME_UNSUPPORTED_OPERATION`
- direct diagnostic assertions still missing for representative `RUNTIME_RUNTIME_TYPE_ERROR` paths

## Phase 5D post-audit notes

Accepted:

- runtime behavior preserved
- messages preserved
- host behavior preserved
- tail-call behavior preserved
- opaque payload internals remain hidden

Residual non-blocking gap:

- `Broader RUNTIME_RUNTIME_TYPE_ERROR branches remain indirectly covered.`

## Phase 5E post-audit notes

Accepted:

- rendering is presentation-only
- runtime behavior preserved
- messages preserved
- opaque payload internals remain hidden
- renderer deterministic

Residual non-blocking gap:

- `Broader RUNTIME_RUNTIME_TYPE_ERROR branches remain indirectly covered.`

## Phase 5 closure summary

Completed:

5A:
runtime diagnostics architecture freeze

5B:
RuntimeDiagnostic foundation

5C:
runtime raise-site conversion

5D:
runtime context enrichment

5E:
runtime diagnostic rendering

Global audit result:

- `PASS_PHASE5_READY_TO_CLOSE`

No required fixes before closure.

Residual non-blocking gaps:

- broader `RUNTIME_RUNTIME_TYPE_ERROR` branch coverage

## Phase 6A post-audit notes

Phase:

- 6A Stack trace architecture audit

Status:

- completed

Decision:

- `PASS_PHASE_READY_TO_CLOSE`

Audit outcome:

- `PASS_PHASE_READY_TO_CLOSE`

Reasoning summary:

- Runtime behavior currently preserved
- No stack trace implementation exists yet
- Current runtime architecture is compatible with future stack traces
- No Nicole language semantic change required
- No divergence detected with repository specification
- Existing runtime diagnostics architecture can support future frame attachment

## Decision freeze before Phase 6B

FROZEN_DECISION_PHASE6A_1:

- Runtime frames are implementation-level structures only.
- Frames MUST NOT introduce Nicole language semantics.
- Frames are diagnostic/runtime metadata.

FROZEN_DECISION_PHASE6A_2:

- Frame creation points are limited to:
- `_invoke_word(...)`
- `_execute_call(...)`
- `_invoke_runtime_quote_value(...)`
- `_execute_host_call(...)`
- No additional frame creation points unless explicitly reviewed.

FROZEN_DECISION_PHASE6A_3:

- _FramePropagationSignal MUST remain a propagation mechanism only.
- It MUST NOT become a runtime frame object.

FROZEN_DECISION_PHASE6A_4:

- Tail-call optimization behavior remains unchanged.
- Self-tail-call loops MUST NOT generate synthetic recursive frame growth.
- Future stack traces should preserve compact behavior.

FROZEN_DECISION_PHASE6A_5:

- RuntimeStack remains a value stack only.
- RuntimeStack MUST NOT become a diagnostic stack container.

FROZEN_DECISION_PHASE6A_6:

- operation strings inside RuntimeDiagnostic MUST NOT be used as frame replacements.
- Future RuntimeFrame data remains separate.

FROZEN_DECISION_PHASE6A_7:

- Locals snapshot behavior is deferred.
- No automatic capture policy is frozen yet.

Residual gap:

- Bundle used during audit did not allow complete local replay because:
- src/nicole/lexer.py was absent.
- Audit relied on:
- supplied runtime files
- supplied test outputs
- AUDIT_STATE.txt

Residual gap:

- Future design decisions still required:
- quotation frame policy
- host frame policy
- locals snapshot policy
- tail-call trace representation
- renderer formatting policy

## Runtime trace constraint

Future Nicole stack traces must not break existing self-tail-call behavior.

Constraint:

- self-tail-calls must not accumulate unbounded logical frames
- compact traces should represent optimized self-tail-calls without pretending every optimized iteration still exists as a full frame
- debug traces may expose optimization information later, but this is deferred

## Future freezes required before later phases

Before Phase 3:

- completed by `Decision freeze before Phase 3A`
- implementation must follow the frozen `Diagnostic`, `DiagnosticError`, compatibility, code naming, rendering ownership, ABI/source-less, and pipeline policies above

Before Phase 4:

- completed by `Decision freeze before Phase 4A`
- multi-file merge model: parse independently and merge declarations only
- duplicate file policy: deduplicate by resolved path
- module collision policy: no new language/module semantics are introduced in Phase 4
- symlink policy: do not follow directory symlinks
- wrong-extension policy: explicit wrong-extension file is an error
- `CheckedProgram` provenance direction: consider backward-compatible `source_files` retention

Before Phase 5:

- freeze runtime diagnostic object shape
- freeze runtime raise/return policy
- freeze stack snapshot sanitization policy
- freeze locals snapshot default/debug-only policy
- freeze Python host exception exposure policy

Before Phase 7:

- freeze `NicoleInterpreter` constructor shape
- freeze how runtime bindings are provided
- freeze whether `run_export(...)` becomes a facade over `NicoleInterpreter`

Before Phase 8:

- Phase 8 name: User class API / `NicoleApplication` facade
- objective: thin ergonomic facade for experimentation
- layering: `NicoleCompiler -> CheckedProgram -> NicoleInterpreter -> NicoleApplication`
- `NicoleApplication` is orchestration only
- constructor stores configuration only
- constructor does not compile or run
- `compile() -> CheckedProgram` compiles paths and stores `CheckedProgram`
- `run(export_name, *args) -> object` lazily compiles if needed
- `run()` creates a fresh `NicoleInterpreter` per call
- `host_bindings` may be `None`, `Mapping[str, Callable[..., object]]`, or `RuntimeHostBindings`
- if `host_bindings` is `None`, use `RuntimeHostBindings({})`
- if `host_bindings` is already `RuntimeHostBindings`, reuse it
- if `host_bindings` is a mapping, wrap it in `RuntimeHostBindings(host_bindings)`
- no host ABI inference
- no automatic `HostContract` generation from Python callables
- no signature reflection
- no debugger/session/VM/profiler/renderer behavior
- no implicit default entrypoint
- `@app.main` is passed through as a normal export name
- errors propagate unchanged
- no fake spans/traces/frames
- package-root export decision is allowed only for `NicoleApplication` if needed
- defer `host_object` unless explicitly approved after compiler/interpreter APIs are stable

Phase 8A tracking:

- implementation commit: `484925f136bfab7145405deb133689987999482d`
- Phase 8A implemented
- `NicoleApplication` introduced
- orchestration-only architecture preserved
- constructor remains lazy
- `CheckedProgram` caching added only at application level
- fresh `NicoleInterpreter` created per run
- runtime/checker separation preserved
- no VM/session semantics introduced
- no host ABI inference introduced
- package-root exports remain unchanged
- audit result: `PASS_READY_FOR_TRACKING`
- audit notes:
- focused tests added
- full suite passing (`888 passed`)
- residual non-blocking test-depth gaps:
- `checked` read-only behavior not explicitly asserted
- `host_contract` forwarding not explicitly asserted

Phase 8 closeout:

- final result: `PASS_PHASE_READY_TO_CLOSE`
- `NicoleApplication` validated as thin orchestration facade
- layering preserved: `NicoleCompiler -> CheckedProgram -> NicoleInterpreter -> NicoleApplication`
- runtime/checker separation preserved
- no VM/session semantics introduced
- no debugger/profiler/renderer semantics introduced
- no host ABI inference introduced
- no reflection-based behavior introduced
- no implicit entrypoint behavior introduced
- `CheckedProgram` remains passive
- fresh `NicoleInterpreter` per run preserved
- full suite passing: `888 passed`
- implementation commit: `484925f136bfab7145405deb133689987999482d`
- tracking acceptance commit: `6090f9b2f61ac26388909ccae57f6208a20ff463`
- residual non-blocking risks:
- `checked` read-only behavior not explicitly asserted in tests
- `host_contract` forwarding not explicitly asserted in tests

Before Phase 9:

- Phase 9 objective:
- a small corpus of realistic Nicole programs
- executable end-to-end
- automatically tested
- executed through `NicoleApplication`
- designed to expose ergonomics and semantic friction
- Phase 9 is NOT:
- marketing demos
- duplicated unit tests
- a framework layer
- a runtime redesign
- a VM/session system
- a host-binding showcase where Python performs business logic
- frozen examples:
- `birthday_cli`
- `file_report`
- `http_status_checker`
- `time_tracker`
- deferred:
- `csv_contact_import`
- host binding rule:
- host bindings expose environment access only
- allowed host responsibilities:
- console I/O
- filesystem access
- HTTP access
- controlled date/time access
- narrowly-scoped parsing primitives only if Nicole lacks them
- forbidden host responsibilities:
- business logic in Python
- age calculation in Python
- HTTP status classification in Python
- report generation in Python
- validation logic hidden in Python
- bypassing Nicole execution
- test freeze rules:
- all examples must be automatically tested
- examples belong to the normal pytest suite
- tests must be deterministic
- no external internet dependency
- no uncontrolled system clock
- no uncontrolled filesystem state
- network examples use a local server or deterministic fake binding
- filesystem examples use `tmp_path`
- console input/output must be simulated
- tests must assert actual Nicole-produced behavior
- examples must fail if Nicole logic does not execute
- repository structure freeze:
- `examples/<example_name>/main.nic`
- `examples/<example_name>/README.md`
- `tests/examples/test_<example_name>.py`
- no shared examples framework
- bindings defined locally in `tests/examples`
- examples remain small and focused
- explicit non-goals:
- no new Nicole semantics
- no source-string `NicoleApplication` API
- no package export redesign
- no runtime/session semantics
- no hidden helper framework
- no implicit network access
- no broad diagnostic snapshot testing
- no examples relying on unimplemented text/date semantics
- audit result: `READY_FOR_PHASE9_FREEZE`

## Change log

| Date | Commit | Change | Tests | Notes |
|---|---|---|---|---|
| - | - | - | - | - |
| 2026-05-23 | `13e81bf865c1a9c86f32e47c350b1154fd6061aa` | Phase 1A implementation prepared: source.py, SourceSpan compatibility, lexer range spans, Phase 1A tests | 707 passed | Post-audit found no blocking issues |
| 2026-05-23 | - | Phase 2 propagation audit and convention freeze | 707 passed | Documentation-only refinement before implementation |
| 2026-05-23 | `d4e3bc8cb661a17a54bc6ca3cdcc489fee8b2096` | Phase 2B/2C.1 implementation prepared: parser span helpers and declaration range propagation | 718 passed | Post-audit found no blocking issues |
| 2026-05-23 | `f96f232ce737bfde3a730796908cec6fe6ada844` | Phase 2B/2C.2 implementation prepared: structured node range propagation | 724 passed | Post-audit found no blocking issues |
| 2026-05-23 | `fa9490afd95b55f4010324a64faabec3dea2c2fd` | Phase 2B/2C.3 implementation prepared: BlockNode range propagation | 729 passed | Post-audit found no blocking issues |
| 2026-05-23 | `ee39540a9f2c53a48c4fdd9a69407301c02db09f` | Phase 2B/2C.4 implementation prepared: IfNode range propagation | 733 passed | Post-audit found no blocking issues; existing required-else grammar preserved |
| 2026-05-23 | `16605aca910b6a796c9bb7e2dbdcbf2a38963c6b` | Phase 2B/2C.5 implementation prepared: CaseNode, CaseBranchNode and constructor PatternNode range propagation | 743 passed | Post-audit found no blocking issues; pattern grammar preserved |
| 2026-05-23 | `a84bfd0bfd47267afc2ef7e4573630b424b21e5c` | Phase 2D implementation prepared: builtin symbols and helpers use `<builtin>` provenance | 746 passed | Post-audit found no blocking issues; host provenance remains deferred |
| 2026-05-23 | `ca63c59fb5866e9da567f64b5f8824be50550c1f` | Phase 2B/2C.6 implementation prepared: ParameterNode, TypeNode, TypedEmptyListNode and TypedEmptyMapNode range propagation | 750 passed | Post-audit found no blocking issues; grammar preserved |
| 2026-05-23 | `3667bc0d4aa729e1f679e809caabe576d600524c` | Phase 3A documentation freeze integrated into later tracking: diagnostic model decisions were finalized and carried into Phase 3B implementation | 760 passed | No standalone pending implementation commit; freeze is reflected by the Phase 3B foundation commit |
| 2026-05-23 | `3667bc0d4aa729e1f679e809caabe576d600524c` | Phase 3B implemented and committed: `Diagnostic`, `DiagnosticError`, compile-time diagnostic enums, compatibility-layer exception subclasses, and one-diagnostic policy enforcement fix | 760 passed | Commit `feat: add structured diagnostic foundation`; Phase 3 remains in progress for 3C+ |
| 2026-05-23 | `e6e1b8178f89e094f53d40d8a417a776a1f2f7b4` | Phase 3C implemented and committed: lexer/parser `LexError` and `ParseError` now attach structured diagnostics with stable codes and span provenance while preserving legacy behavior | 770 passed | Commit `feat: attach lexer parser diagnostics`; Phase 3 remains in progress and Phase 3D is next |
| 2026-05-23 | `8c78bf445a5f1bd86ec0546b67da68906912e779` | Phase 3D implemented and committed: SymbolError, ResolutionError and CheckerError now attach structured diagnostics with stable codes and source-aware spans while preserving legacy compatibility | 781 passed | Commit `feat: attach static analysis diagnostics`; Phase 3 remains in progress |
| 2026-05-24 | `ee527a3ded498517118feec06367f74d9ee964c6` | Phase 3E implemented and committed: HostABIError paths now attach structured diagnostics with explicit ABI codes and source-aware spans while preserving legacy compatibility | 785 passed | Commit `feat: attach host abi diagnostics`; Phase 3 remains in progress |
| 2026-05-23 | `51a3f1aa88e80ee9df9d4de1c8a1a9e390bbbe50` | Phase 3F implemented and committed: diagnostic renderer with excerpts, caret formatting, clipping and compatibility-preserving presentation support | 799 passed | Commit `feat: add diagnostic renderer`; Phase 3 remains in progress and Phase 3G is next |
| 2026-05-24 | `5c58008acebf324d35793a239e24bf748e462c1d` | Phase 3G implemented and committed: remaining legacy compile-time diagnostic assumptions cleaned up and Phase 3 structured diagnostics finalized | 802 passed | Commit `chore: finalize phase3 diagnostic cleanup`; Phase 3 ready for closure tracking |
| 2026-05-24 | - | Phase 3 closed after tracking update; Phase 4 is next | 802 passed | Tracking-only closure after Phase 3G commit |
| 2026-05-24 | - | Phase 4A tracking freeze integrated: scope limited to multi-file compiler/loader, Phase 4B-4H breakdown recorded, invariants and non-goals documented | `python -m pytest -q` failed: `No module named pytest` | Documentation-only update; implementation remains pending |
| 2026-05-24 | `267ea2fc20b5696b15b744566620452c6833feb9` | Phase 4B implemented and committed: source-aware lexer entrypoint added with `lex_source(source_file: SourceFile)`, `Lexer.tokenize_source(source_file: SourceFile)`, and preserved `lex(source: str)` / `Lexer.tokenize(source: str)` compatibility | `./.venv/bin/python -m pytest tests/test_lexer.py -q`: 37 passed; `./.venv/bin/python -m pytest -q`: 806 passed | Commit `feat: add source-aware lexer entrypoint`; Phase 4C compiler skeleton for explicit files is next |
| 2026-05-24 | `30cfeab08d8743f41d0f844bb4c56853f9696788` | Phase 4C implemented and committed: explicit file compiler skeleton added with `src/nicole/compiler.py`, `NicoleCompiler`, `NicoleCompiler.compile(input_path)`, `NicoleCompiler.compile_file(file_path)`, `compile_path(input_path, *, host_contract=None)`, physical `SourceFile` compilation flow, and structured `PIPELINE_*` input diagnostics | `./.venv/bin/python -m pytest tests/test_compiler.py -q`: 5 passed; `./.venv/bin/python -m pytest -q`: 811 passed | Commit `feat: add explicit file compiler skeleton`; Phase 4D recursive directory loader and input normalization is next |
| 2026-05-24 | `da0cc8523f808a8fac824c385b1361d710f6c2b8` | Phase 4D implemented and committed: compiler input normalization added with `NicoleCompiler.compile(...)` accepting `str | Path | Iterable[str | Path]`, recursive `*.nic` discovery, deterministic resolved-path ordering, `Path.resolve()` deduplication, blocked symlink-directory traversal, accepted symlinked `.nic` files by design, structured `PIPELINE_*` input diagnostics, and temporary `PIPELINE_MULTIFILE_NOT_IMPLEMENTED` gate for multiple discovered files | `./.venv/bin/python -m pytest tests/test_compiler.py -q`: 10 passed; `./.venv/bin/python -m pytest -q`: 816 passed | Commit `feat: add compiler input normalization`; post-commit audit `PASS_READY_FOR_TRACKING`; residual risk: symlinked `.nic` file acceptance is not yet directly tested; Phase 4E AST merge and full pipeline reuse is next |
| 2026-05-24 | - | Phase 4E design freeze corrected after repository audit: merge by declarations in normalized file order, rebuild `ProgramNode.words`, keep representative multi-file `ProgramNode.span`, add `_analyze_program(...)`, keep `analyze_program(...)` compatibility with `source_files=()`, and preserve current duplicate/import/export behavior | - | Tracking-only design correction after audit result `DESIGN_NEEDS_CORRECTION_BEFORE_IMPLEMENTATION`; Phase 4E implementation remains next |
| 2026-05-24 | `bb695b07afaf879b5ad9ec2dfb88988745a5102f` | Phase 4E implemented and committed: each source file is parsed independently, merged `ProgramNode` analysis is enabled without source concatenation, merged declarations preserve normalized order, `ProgramNode.words` is rebuilt, original declaration/node provenance is preserved, representative multi-file `ProgramNode.span` is used, `_analyze_program(...)` reuses the pipeline, `CheckedProgram.source_files` was added, `NicoleCompiler` retains physical source files, `analyze_program(...)` remains backward compatible with `source_files=()`, include declarations remain inert, duplicate module/name/export behavior remains unchanged, and `PIPELINE_MULTIFILE_NOT_IMPLEMENTED` was removed | `./.venv/bin/python -m pytest tests/test_compiler.py -q`: 13 passed; `./.venv/bin/python -m pytest tests/test_pipeline.py -q`: 30 passed; `./.venv/bin/python -m pytest -q`: 821 passed | Commit `feat: merge compiler source programs`; residual risk: representative multi-file `ProgramNode.span` is not authoritative and declaration spans remain authoritative for diagnostics; Phase 5 runtime diagnostics is next |
| 2026-05-24 | - | Phase 5A runtime audit accepted and architecture freeze recorded: runtime diagnostics remain structured-data only, `RuntimeError` stays public as a compatibility-wrapper carrier, `RUNTIME` phase/codes and span policy are frozen, and stack traces/frame history/locals snapshots remain out of scope for Phase 5 | - | Tracking-only freeze after audit result `RUNTIME_READY_FOR_DESIGN_FREEZE`; Phase 5B runtime diagnostic foundation is next |
| 2026-05-24 | `10d186b146eb986b6abe5e7b76698fa72c089553` | Phase 5B implemented and committed: `RuntimeDiagnosticSeverity`, `RuntimeDiagnosticPhase`, `RuntimeDiagnostic`, and `runtime_diagnostic(...)` were added; `RuntimeError` remains public and string-compatible while now carrying `diagnostic`, `diagnostics`, and `message`; default runtime diagnostics use `ERROR`, `RUNTIME`, `RUNTIME_ERROR`, and `span=None` | `./.venv/bin/python -m pytest tests/test_runtime.py -q`: 201 passed; `./.venv/bin/python -m pytest -q`: 825 passed | Commit `feat: add runtime diagnostic foundation`; runtime execution, runtime raise-site behavior, host behavior, and tail-call behavior remain unchanged; no stack traces, frame objects, or locals snapshots were added; Phase 5C convert runtime raise sites is next |
| 2026-05-24 | `39012f3bab7b73db9c39d00005ff0b4c0033f0f8` | Phase 5C implementation completed: runtime raise sites now attach structured diagnostics | `205 passed`; `829 passed` | Post-audit passed; residual coverage gaps deferred |
| 2026-05-24 | `db43fa1f23433b839b620e538212ecd0af1745c7` | Phase 5D implementation accepted and tracked | `209 passed`; `833 passed` | Commit `feat: enrich runtime diagnostic context`; post-audit result accepted; residual coverage gap remains non-blocking |
| 2026-05-24 | `7b4a14f2e60e7d3386403ef77d29d22a49b5a33c` | Phase 5E implementation accepted | `218 passed`; `842 passed` | Commit `feat: render runtime diagnostics` |
| 2026-05-24 | - | Phase 5 closed after complete audit | `218 passed`; `842 passed` | Global closeout result `PASS_PHASE5_READY_TO_CLOSE`; no required fixes before closure |
| 2026-05-24 | - | Phase 6A stack trace architecture audit completed and architecture freezes recorded before implementation | `218 passed`; `842 passed` | Tracking-only closeout with decision `PASS_PHASE_READY_TO_CLOSE`; Phase 6B RuntimeFrame and RuntimeStackTrace foundation implementation is next |
| 2026-05-25 | `c0b94e6fbe41316b4e5968ce52e6bae03c8c0bda` | Phase 6B implemented and committed: RuntimeFrameKind added with WORD/QUOTATION/HOST; RuntimeFrame added as immutable metadata-only structure; RuntimeStackTrace added as immutable container with append/extend returning new instances | `./.venv/bin/python -m pytest tests/test_runtime.py -q`: 224 passed; `./.venv/bin/python -m pytest -q`: 848 passed | Commit `feat: add runtime stack trace foundation`; no diagnostics trace attachment; no RuntimeError trace attachment; no renderer changes; no locals snapshots; no frame history; runtime behavior preserved; Phase 6C frame lifecycle attachment is next |
| 2026-05-25 | `700654d9e99225cff9337b16bb2f08a797a0447a` | Phase 6C implemented and committed: RuntimeStackTrace threaded internally through runtime execution lifecycle; frame creation attached at frozen points with duplicate quotation frame removed from `_execute_call(...)` and kept in `_invoke_runtime_quote_value(...)` | `./.venv/bin/python -m pytest tests/test_runtime.py -q`: 226 passed; `./.venv/bin/python -m pytest -q`: 850 passed | Commit `feat: attach runtime frame lifecycle`; WORD frames created in `_invoke_word(...)`; HOST frames created in `_execute_host_call(...)`; QUOTATION frames created only in `_invoke_runtime_quote_value(...)`; traces remain internal and are not attached to RuntimeDiagnostic or RuntimeError; no renderer changes; no locals snapshots; no frame history; self-tail-call compactness preserved; runtime behavior preserved; Phase 6D RuntimeDiagnostic and RuntimeError trace attachment is next |
| 2026-05-25 | `72b63fb01d70d4ee8e12db19b0ab752c7f7fcd86` | Phase 6D implemented and committed: RuntimeDiagnostic and RuntimeError now carry structured RuntimeStackTrace attachment without changing legacy RuntimeError string behavior | `./.venv/bin/python -m pytest tests/test_runtime.py -q`: 240 passed; `./.venv/bin/python -m pytest -q`: 864 passed | Commit `feat: attach traces to runtime diagnostics`; RuntimeDiagnostic carries optional RuntimeStackTrace metadata; `runtime_diagnostic(...)` accepts optional trace data; RuntimeError preserves diagnostic trace through diagnostics tuple; renderer does not render traces; traces remain structured-only metadata; trace is attached only where natural runtime trace context exists; no fake traces for stack pop/peek, host binding constructor validation, or missing export API errors; checker/runtime separation preserved after test rewrite; defensive runtime guards remain, but statically invalid Nicole programs are not tested via checker bypass in Phase 6D tests; Phase 6E runtime trace rendering integration is next |
| 2026-05-25 | `59166a394f9615a13dd2e0ddb7877ee2b3573708` | Phase 6E implemented and committed: runtime diagnostic renderer now renders RuntimeStackTrace when present using frozen deterministic trace formatting while preserving legacy RuntimeError compatibility and no-trace rendering behavior | `./.venv/bin/python -m pytest tests/test_runtime.py -q`: 248 passed; `./.venv/bin/python -m pytest -q`: 872 passed | Commit `feat: render runtime stack traces`; trace rendering integrated; no ANSI; no locals snapshots; no frame history; no semantic changes; renderer remains presentation-only; Phase 6F final audit and closeout is next |
| 2026-05-25 | `2ebf6485e77cd84491dd526038fec1380505bede` | Phase 6F cleanup completed: runtime trace tests aligned with checker/runtime boundary policy by removing checker-bypass execution of statically invalid Nicole programs through run_export(...) | `./.venv/bin/python -m pytest tests/test_runtime.py -q`: 248 passed; `./.venv/bin/python -m pytest -q`: 872 passed | Commit `test: align runtime trace tests with checker boundaries`; helper-level runtime defensive tests preserved; runtime-boundary tests preserved; host-boundary tests preserved; Phase 6 officially ready to close |
| 2026-05-25 | `6cf78848f7cdac9d24487783093366a0df4978d1` | Phase 7A audit acceptance recorded: `NicoleInterpreter` introduced, `run_export(...)` compatibility preserved, interpreter remains minimal, `CheckedProgram` remains passive, and no runtime redesign or VM/session semantics were introduced | `PASS_READY_FOR_TRACKING` | Tracking-only acceptance for implementation commit `6cf78848f7cdac9d24487783093366a0df4978d1`; package-root export decision deferred to Phase 8 |
| 2026-05-25 | - | Phase 8 architecture freeze recorded: thin `NicoleApplication` facade approved as orchestration-only convenience over `NicoleCompiler`, `CheckedProgram`, and `NicoleInterpreter` with lazy compile-on-run behavior and unchanged error propagation | - | Tracking-only freeze; no host ABI inference; no signature reflection; no debugger/session/VM/profiler/renderer behavior; package-root export allowed only for `NicoleApplication` if needed; Phase 8A implementation is next |
| 2026-05-25 | `484925f136bfab7145405deb133689987999482d` | Phase 8A audit acceptance recorded: `NicoleApplication` introduced; orchestration-only architecture preserved; constructor remains lazy; application-level `CheckedProgram` caching added; fresh `NicoleInterpreter` is created per run; runtime/checker separation preserved; no VM/session semantics or host ABI inference were introduced; package-root exports remain unchanged | `./.venv/bin/python -m pytest tests/test_application.py -q`: 11 passed; `./.venv/bin/python -m pytest -q`: 888 passed; `PASS_READY_FOR_TRACKING` | Tracking-only acceptance for implementation commit `484925f136bfab7145405deb133689987999482d`; residual non-blocking test-depth gaps: `checked` read-only behavior not explicitly asserted and `host_contract` forwarding not explicitly asserted |
| 2026-05-25 | `6090f9b2f61ac26388909ccae57f6208a20ff463` | Phase 8 closed after final closeout audit: `NicoleApplication` validated as a thin orchestration facade; layering preserved as `NicoleCompiler -> CheckedProgram -> NicoleInterpreter -> NicoleApplication`; runtime/checker separation preserved; `CheckedProgram` remains passive; fresh `NicoleInterpreter` per run preserved; no VM/session semantics, debugger/profiler/renderer semantics, host ABI inference, reflection-based behavior, or implicit entrypoint behavior were introduced | `./.venv/bin/python -m pytest -q`: 888 passed; `PASS_PHASE_READY_TO_CLOSE` | Tracking-only closeout after final audit; residual non-blocking risks remain limited to missing explicit assertions for `checked` read-only behavior and `host_contract` forwarding |
| 2026-05-25 | - | Phase 9 freeze recorded: tested end-to-end examples corpus approved as a small, realistic, automatically tested set of Nicole programs executed through `NicoleApplication` to expose ergonomics and semantic friction | `READY_FOR_PHASE9_FREEZE` | Tracking-only freeze; frozen examples: `birthday_cli`, `file_report`, `http_status_checker`, `time_tracker`; `csv_contact_import` deferred; host bindings remain environment-only with business logic forbidden in Python; examples stay in the normal pytest suite with deterministic local test controls and no shared framework |
