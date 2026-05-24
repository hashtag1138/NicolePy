# NicolePy milestone — diagnostics, multi-file compilation, explicit runtime

## Baseline

- Current date: 2026-05-23
- Current HEAD: `9f7e3279b6c9a703a051dad345643b38b5b4b08c`
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
| 3. Structured compilation diagnostics | in_progress | `fdcd627902baad3c3f0a695716dfb36acc17f685` | Phase 3B, 3C, and 3D prepared: lexer/parser/symbols/resolver/checker errors now attach structured diagnostics | 781 passed | Phase 3D implementation prepared; Phase 3E+ remains pending |
| 4. Multi-file compiler | pending | - | Add explicit compiler/loader API for files and directories | - | Keep include semantics deferred |
| 5. Runtime diagnostics | pending | - | Add structured runtime diagnostic payloads | - | Depends on phase 3 and 4 |
| 6. Nicole stack trace | pending | - | Add Nicole runtime frame stack trace model | - | Depends on phase 5 |
| 7. Interpreter API | pending | - | Add explicit `NicoleInterpreter` API on `CheckedProgram` | - | Keep `run_export(...)` compatibility |
| 8. User class API | pending | - | Add ergonomic app-level wrapper usage patterns | - | Thin convenience layer |
| 9. Optional host method binding | deferred | - | Optional decorator/introspection binding model | - | Deferred by decision |

## Audit findings summary

- Source model is now file-bound and range-based.
- Tokens carry file-bound end-exclusive spans.
- AST nodes are range-aware according to Phase 2 frozen conventions.
- Builtin symbols and builtin helper nodes use `<builtin>` provenance.
- Host provenance remains resolver/contract-owned and deferred.
- Lexer and parser now attach structured diagnostics (phase/code/span) while preserving legacy exception compatibility.
- Symbol collection, resolver, and checker now attach structured diagnostics; ABI and runtime diagnostics are still pending follow-up phases.
- No `NicoleCompiler` exists yet.
- No real `NicoleInterpreter` API exists yet.
- Runtime errors still lack structured span/operation/stack trace diagnostics.
- Documentation target references remain inconsistent and should be realigned later in a dedicated documentation cleanup patch.

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

## Next patch

Phase 3E — adapt host ABI and pipeline pass-through policy.

Scope:
- adapt `HostABIError` raise paths to structured diagnostics
- verify pipeline pass-through policy for phase-specific `DiagnosticError` subclasses
- preserve source-less ABI diagnostics where no Nicole source span exists
- prefer real Nicole source spans when available
- preserve legacy behavior and one-diagnostic policy

Non-goals:
- no runtime diagnostics yet
- no multi-file compiler yet
- no interpreter API yet
- no host method binding yet
- no renderer/caret/excerpt work

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

- freeze multi-file merge model
- freeze duplicate file policy
- freeze module collision policy
- freeze symlink policy
- freeze wrong-extension policy
- freeze whether `CheckedProgram` retains source files or a source map

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

- freeze whether the user class API is documentation-only, a thin helper, or a public library API
- defer `host_object` unless explicitly approved after compiler/interpreter APIs are stable

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
| 2026-05-23 | pending | Phase 3A diagnostic model freeze prepared | 750 passed | Documentation-only design freeze after Phase 3 audit |
| 2026-05-23 | `3667bc0d4aa729e1f679e809caabe576d600524c` | Phase 3B implemented and committed: `Diagnostic`, `DiagnosticError`, compile-time diagnostic enums, compatibility-layer exception subclasses, and one-diagnostic policy enforcement fix | 760 passed | Commit `feat: add structured diagnostic foundation`; Phase 3 remains in progress for 3C+ |
| 2026-05-23 | `e6e1b8178f89e094f53d40d8a417a776a1f2f7b4` | Phase 3C implemented and committed: lexer/parser `LexError` and `ParseError` now attach structured diagnostics with stable codes and span provenance while preserving legacy behavior | 770 passed | Commit `feat: attach lexer parser diagnostics`; Phase 3 remains in progress and Phase 3D is next |
| 2026-05-24 | pending | Phase 3D implementation prepared: `SymbolError`, `ResolutionError`, and `CheckerError` now attach structured diagnostics with stable codes while preserving legacy exception compatibility | 781 passed | Commit pending; Phase 3 remains in progress and Phase 3E is next |
