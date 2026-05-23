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

Parameters and types:

- `ParameterNode` ends at type end.
- `TypeNode` spans full type expression.
- Constructor patterns span through closing delimiter.

Blocks:

- `BlockNode` is container-derived.
- Non-empty blocks start at first contained token.
- Empty blocks use delimiter-based spans if available.
- Otherwise empty blocks use zero-length spans.

Case branches:

- `CaseBranchNode` starts at pattern start.
- `CaseBranchNode` ends at branch body boundary.

Provenance:

- builtin symbols must use `<builtin>`
- host provenance behavior must be explicit
- synthetic AST nodes preserve synthetic provenance
- no node may silently downgrade provenance precision

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
| 2. Tokens + AST spans | in_progress | pending commit | Phase 2B/2C.3 implemented: BlockNode range propagation | 729 passed | Post-patch audit passed; awaiting commit |
| 3. Structured compilation diagnostics | pending | - | Introduce structured diagnostics model and formatting | - | Depends on phase 2 |
| 4. Multi-file compiler | pending | - | Add explicit compiler/loader API for files and directories | - | Keep include semantics deferred |
| 5. Runtime diagnostics | pending | - | Add structured runtime diagnostic payloads | - | Depends on phase 3 and 4 |
| 6. Nicole stack trace | pending | - | Add Nicole runtime frame stack trace model | - | Depends on phase 5 |
| 7. Interpreter API | pending | - | Add explicit `NicoleInterpreter` API on `CheckedProgram` | - | Keep `run_export(...)` compatibility |
| 8. User class API | pending | - | Add ergonomic app-level wrapper usage patterns | - | Thin convenience layer |
| 9. Optional host method binding | deferred | - | Optional decorator/introspection binding model | - | Deferred by decision |

## Audit findings summary

- Current `SourceSpan` is point-only and file-less.
- Tokens and AST are partially source-aware.
- Diagnostics are currently exception/message based.
- No structured `Diagnostic` model exists.
- No `NicoleCompiler` exists.
- No real `NicoleInterpreter` API exists.
- Runtime errors lack span/operation/stack trace.
- Tests are green at audit baseline.
- Documentation target references are inconsistent and should be realigned later in a dedicated documentation cleanup patch, not during Phase 1A.

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

Phase 1A — lexer-origin source model.

Scope:
- introduce/extend source primitives
- make spans file-bound and range-based
- preserve compatibility accessors `line`, `column`, `offset`
- keep tests green

Non-goals:
- no rich diagnostics yet
- no multi-file compiler yet
- no runtime changes yet
- no interpreter API yet

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
- builtin provenance wiring may require later cleanup
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

## Runtime trace constraint

Future Nicole stack traces must not break existing self-tail-call behavior.

Constraint:

- self-tail-calls must not accumulate unbounded logical frames
- compact traces should represent optimized self-tail-calls without pretending every optimized iteration still exists as a full frame
- debug traces may expose optimization information later, but this is deferred

## Future freezes required before later phases

Before Phase 3:

- freeze compile-time `Diagnostic` fields
- freeze `DiagnosticError` raise/return policy
- freeze compatibility policy for current exceptions and `__str__`
- freeze diagnostic code naming scheme
- freeze source excerpt/caret formatting ownership

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
| 2026-05-23 | pending | Phase 2B/2C.2 implementation prepared: structured node range propagation | 724 passed | Post-audit found no blocking issues |
| 2026-05-23 | pending | Phase 2B/2C.3 implementation prepared: BlockNode range propagation | 729 passed | Post-audit found no blocking issues |
