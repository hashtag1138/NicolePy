# Implementation Roadmap — Nicole v0.14.0 Purity/Effects

## Source of truth

Nicole specification repository:
~/Sources/nicole_language_docs_seed

Specification tag:
v0.14.0-purity-effects

Specification commit:
b8ab130aba6fffad1803f4f948306e47e55d995b

Nicole specification always wins.

NicolePy documentation is not authoritative.

## Current status

Lexer: partial
Parser: partial
AST: partial
Signature collection: partial
Resolver: partial
Checker: partial
Runtime: partial
Host ABI: partial
Higher-order builtins: partial
Result/? : implemented
Purity/effects: missing
DirtyQuote: missing
Purity/effect tests: missing

## Feature dependency graph

```text
dirty token
    ↓
parser modifier support
    ↓
AST effect metadata
    ↓
signature collection
    ↓
resolver propagation
    ↓
host effect metadata
    ↓
checker effect graph
    ↓
SCC inference
    ↓
DirtyQuote
    ↓
HOF effect gating
    ↓
runtime alignment
    ↓
conformance tests
```

## Phase 1 — Lexer / Parser / AST minimal dirty support

### Goal

Add minimal syntax representation for `dirty` and enforce canonical modifier ordering without implementing checker effect inference yet.

### Files likely affected

- `src/nicole/tokens.py`
- `src/nicole/lexer.py`
- `src/nicole/parser.py`
- `src/nicole/ast_nodes.py`
- `tests/test_tokens.py`
- `tests/test_lexer.py`
- `tests/test_parser.py`

### Dependencies

None.

### Required tests

- `dirty` token recognition
- accepted forms: `dirty :`, `pub dirty :`, `export dirty :`
- rejected forms: `dirty pub :`, `dirty export :`, `: dirty foo`
- exact reserved `dirty` rejection in word names, subword names, locals, captures, and output labels

### Risks

- modifier parsing ambiguity
- accidental acceptance of obsolete forms

### Completion criteria

- parser accepts all canonical v0.14.0 forms
- parser rejects invalid ordering forms
- AST stores word-level effect annotation metadata
- reserved exact `dirty` constraints are enforced at parse-time definition points

### Complexity

medium

### Implementation notes

Implemented:

- `TokenKind.DIRTY`
- exact keyword recognition
- parser support:
  - `dirty :`
  - `pub dirty :`
  - `export dirty :`
- invalid modifier ordering rejection
- exact reserved identifier handling
- explicit reserved diagnostics
- `WordDefNode.is_dirty_annotation` metadata
- parser/lexer/AST tests

## Phase 2 — Host ABI effect metadata

### Goal

Require explicit host effect metadata (`pure|dirty`) in host ABI contract, independent from binding availability.

### Files likely affected

- `src/nicole/host_abi.py`
- `src/nicole/pipeline.py`
- `tests/test_host_abi.py`
- `tests/test_pipeline.py`

### Dependencies

Phase 1.

### Required tests

- host contract rejects missing effect metadata
- host contract accepts explicit `effect: pure` and `effect: dirty`
- availability remains independent from effect metadata
- direct optional host call remains invalid in v1
- ABI quote restrictions continue to hold

### Risks

- host fixture breakage in existing tests
- schema migration gaps for host contract construction

### Completion criteria

- host words require explicit effect metadata
- host validation rejects invalid or absent effect metadata
- resolver/checker interfaces can read host effect metadata

### Complexity

medium

### Implementation notes

Implemented:

- HostEffect enum
  - HostEffect.PURE
  - HostEffect.DIRTY

- HostWord.effect mandatory field

- explicit validation in HostWord.__post_init__

- missing effect rejected

- invalid effect rejected

- no implicit default effect

- availability remains independent from effect

- existing ABI restrictions preserved

- all HostWord(...) fixtures updated

- Phase 2 validation matrix added:
  - required + PURE
  - required + DIRTY
  - optional + PURE
  - optional + DIRTY

## Phase 3 — Symbols / Signature collection / Resolver metadata propagation

### Goal

Propagate effect metadata across symbol collection and resolver outputs so checker can consume stable effect annotations.

### Files likely affected

- `src/nicole/symbols.py`
- `src/nicole/signature_collector.py`
- `src/nicole/resolver.py`
- `src/nicole/ast_nodes.py`
- `tests/test_signature_collector.py`
- `tests/test_resolver.py`

### Dependencies

Phase 1 and Phase 2.

### Required tests

- word symbols preserve declared dirty annotation
- export/pub visibility remains preserved alongside effect metadata
- resolver attaches host and user effect metadata to resolved identifiers
- reserved exact `dirty` behavior remains consistent in resolver contexts

### Risks

- resolution schema drift affecting checker/runtime integration
- owner-scope metadata regressions

### Completion criteria

- symbol table carries word effect metadata
- resolver annotations expose effect metadata for checker phase
- no loss of existing visibility and qualification behavior

### Complexity

medium

### Implementation notes

Implemented:

- WordSymbol.declared_dirty metadata

- propagation:
    WordDefNode.is_dirty_annotation
        ↓
    WordSymbol.declared_dirty

- ResolutionInfo metadata:
    - declared_dirty
    - host_effect

- resolver exposes:
    - user declared_dirty
    - host HostEffect

- top-level and subword metadata preserved

- visibility/export/qualification preserved

- metadata only:
    - no inference
    - no SCC
    - no validation
    - no effect graph

## Phase 4 — Checker effect graph and SCC inference

### Goal

Implement static effect analysis: call-graph construction, SCC fixed-point inference, transitive dirty propagation, exact dirty annotation validation.

### Files likely affected

- `src/nicole/checker.py`
- `src/nicole/pipeline.py`
- `tests/test_checker.py`
- `tests/test_pipeline.py`

### Dependencies

Phase 1-3.

### Required tests

- inferred pure + no annotation => valid
- inferred dirty + annotated dirty => valid
- inferred dirty + missing dirty => error
- inferred pure + annotated dirty => error
- pure caller cannot call dirty callee
- host dirty calls propagate transitively
- host pure calls do not introduce impurity
- recursion and mutual recursion use SCC fixed-point inference

### Risks

- SCC algorithm correctness and convergence
- cross-feature regressions in current type checks

### Completion criteria

- checker computes inferred effects for all words
- exact annotation validation is enforced
- pure/dirty call constraints enforced statically
- no runtime effect enforcement added

### Complexity

high

### Implementation notes

Implemented:

- internal effect analysis in checker

- user-word call graph

- qualified-name graph nodes

- Tarjan SCC handling

- host dirty source detection

- transitive dirty inference

- exact annotation validation:
    - inferred dirty + missing annotation
    - inferred pure + redundant dirty

- pure caller -> dirty callee rejection

- conservative if/case branch union

- quotations ignored for Phase 4

- metadata-only analysis state:
    - no SymbolTable mutation
    - no CheckedProgram mutation

- no runtime effect checks

## Phase 5 — DirtyQuote and higher-order effect gating

### Goal

Add `DirtyQuote<{...}>` support and enforce pure/dirty frame restrictions for quote construction/call/HOF usage.

### Files likely affected

- `src/nicole/parser.py`
- `src/nicole/ast_nodes.py`
- `src/nicole/checker.py`
- `src/nicole/standard_symbols.py`
- `tests/test_parser.py`
- `tests/test_checker.py`
- `tests/test_standard_symbols.py`
- `tests/test_pipeline.py`

### Dependencies

Phase 4.

### Required tests

- parse/type support for `DirtyQuote<{...}>`
- `call` on `Quote` remains pure
- `call` on `DirtyQuote` is dirty
- pure frame cannot construct `DirtyQuote`
- pure frame cannot call `DirtyQuote`
- pure frame cannot pass `DirtyQuote` to `list.map/filter/fold/reduce`
- dirty frame may construct/call/pass `DirtyQuote` to those HOFs
- HOFs accept both `Quote` and `DirtyQuote`

### Risks

- quote type compatibility edge cases
- higher-order rule interactions with existing stack/type checks

### Completion criteria

- DirtyQuote is represented in type model and checker
- call/HOF effect gating matches v0.14.0 rules
- no dirty-specific duplicate builtins introduced

### Complexity

high

## Phase 6 — Runtime alignment

### Goal

Align runtime feature support with checker-accepted constructs while keeping runtime effect-agnostic and without runtime dirty validation.

### Files likely affected

- `src/nicole/runtime.py`
- `src/nicole/pipeline.py`
- `tests/test_runtime.py`

### Dependencies

Phase 5.

### Required tests

- runtime supports checker-accepted HOF behavior (`list.map/filter/fold/reduce`)
- runtime Quote/DirtyQuote values execute consistently with static checks
- no runtime purity/effect validation paths are introduced
- existing Result/? runtime behavior remains unchanged

### Risks

- checker/runtime behavior mismatch
- regressions in existing runtime list/map operations

### Completion criteria

- no static/runtime mismatch for accepted programs
- runtime remains effect-agnostic
- unsupported obsolete paths are removed or isolated if conflicting

### Complexity

high

## Phase 7 — Conformance tests and cleanup

### Goal

Finalize conformance coverage and remove obsolete or contradictory behavior after purity/effects implementation is complete.

### Files likely affected

- `tests/test_lexer.py`
- `tests/test_parser.py`
- `tests/test_checker.py`
- `tests/test_pipeline.py`
- `tests/test_host_abi.py`
- `tests/test_runtime.py`
- selective cleanup in `src/nicole/checker.py` and `src/nicole/runtime.py`

### Dependencies

Phase 1-6.

### Required tests

- full dirty syntax matrix
- host effect metadata requirements
- transitive propagation and SCC recursion cases
- Quote/DirtyQuote HOF gating rules
- export effect preservation behavior
- Result/? orthogonality to effect
- subword dirty propagation and non-propagation when unused
- ABI quote restrictions for Quote and DirtyQuote

### Risks

- brittle assertions around diagnostic text
- latent incompatibilities from integrated changes

### Completion criteria

- conformance suite passes end-to-end
- no known contradictions with v0.14.0 purity/effects remain
- roadmap phases can be marked implemented and audited

### Complexity

medium

## Milestones

M1
syntax represented

Status: completed

M2
effect metadata propagated

Status: completed

M3
effect checker working
Status: completed

M4
DirtyQuote working

M5
runtime aligned

M6
full conformance suite passing

## Phase status tracking

- [x] Phase 1
Status: implemented

- [x] Phase 2
Status: implemented

- [x] Phase 3
Status: implemented

- [x] Phase 4
Status: implemented

- [ ] Phase 5
Status: not started

- [ ] Phase 6
Status: not started

- [ ] Phase 7
Status: not started

Status values:
- not started
- in progress
- implemented
- audited
- committed

## Completed decisions

- dirty exact identifier reserved
- dirty explicit / pure implicit
- exact annotation validation
- host-only impurity source
- transitive propagation
- SCC inference
- DirtyQuote model
- static-only effect validation
- no runtime dirty checks

## Out of scope

- runtime dirty validation
- new language syntax
- effect inference redesign
- changing Result/? semantics
- changing ABI rules
