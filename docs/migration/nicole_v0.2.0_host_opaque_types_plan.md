# NicolePy Migration Plan
Target: Nicole v0.2.0-host-opaque-types

## Status legend

- pending
- in_progress
- completed
- blocked

---

## Global objective

Align NicolePy with Nicole spec `v0.2.0-host-opaque-types` while preserving existing stable behavior outside the scoped feature.  
Migration is incremental, test-driven, and phase-isolated.  
No Nicole source syntax is introduced for opaque type declarations.

---

## Architecture constraints

- Nicole specification is the source of truth.
- Host opaque types are declared by host contract only.
- Canonical names are `host.*` and identity is nominal.
- No host opaque type aliases.
- Keep quote prohibition across ABI unchanged.
- Keep map key restriction unchanged: `Int | String | Bool`.
- Opaque types may be map values only.
- Effect behavior remains unchanged: opaque values are data; `host.*` calls remain impurity sources.
- Do not use `standard_symbols.py` as opaque type registry.
- Everything provable statically must be validated statically.

---

## Phase 1 — ABI opaque type registry

Status: completed

Purpose:
Introduce a minimal host-contract registry for declared host opaque types using canonical `host.*` names.

Files:
- `src/nicole/host_abi.py`
- `tests/test_host_abi.py`
- `tests/test_pipeline.py` (only if constructor/public surface exposure is covered there)

Tests:
- Accept declared opaque type names under `host.*`.
- Reject non-`host.*` opaque type names.
- Reject duplicate opaque type declarations.
- Confirm no alias mechanism is introduced.

Expected result:
Host contract can represent declared opaque types independently from host words, without changing checker/runtime behavior yet.

Risks:
- Over-designing registry structure.
- Coupling opaque type registry with unrelated symbol systems.

Notes:
Keep this phase model-only and backward compatible for existing host-word usage.

---

## Phase 2 — ABI signature validation

Status: completed

Purpose:
Update ABI-visible signature validation to accept declared opaque types and reject undeclared opaque types.

Files:
- `src/nicole/host_abi.py`
- `tests/test_host_abi.py`
- `tests/test_pipeline.py`

Tests:
- Host word signatures accept declared opaque types.
- Host word signatures reject undeclared opaque types.
- Export signatures accept declared opaque types.
- Export signatures reject undeclared opaque types.
- Preserve quote prohibition across ABI.
- Preserve map key rule; reject opaque map keys and accept opaque map values.

Expected result:
ABI layer is spec-aligned for host opaque type declarations and ABI-visible type usage.

Risks:
- Accidentally relaxing quote prohibition.
- Accidentally allowing arbitrary unknown nominal types.

Notes:
Do not freeze transitional behavior; assert final ABI invariants only.

---

## Phase 3 — Checker support

Status: completed

Purpose:
Add checker support for host opaque types, including static admission rules and static rejections.

Files:
- `src/nicole/checker.py`
- `src/nicole/pipeline.py` (if checker needs explicit contract context wiring)
- `tests/test_checker.py`
- `tests/test_pipeline.py` (for integrated static checks)

Tests:
- Admit declared `host.*` types in signatures, locals, stack values, quotations, `List<T>`, `Result<T,E>`, and map values.
- Reject undeclared `host.*` types in checker-visible type positions.
- Reject arbitrary unknown nominal types (`Foo`, `Bar`, `Baz`) using normal unknown-type diagnostics.
- Preserve map key restriction and reject opaque keys.
- Reject `=` and `!=` on opaque operands statically.
- Confirm effect behavior remains unchanged.

Expected result:
Static type validation is spec-aligned for host opaque type usage and restrictions.

Risks:
- Regressions in existing type validation error paths.
- Missing contract context in checker call chain.

Notes:
This phase is where equality/inequality rejection belongs by policy.

---

## Phase 4 — Runtime opaque representation

Status: completed

Purpose:
Introduce runtime representation and nominal runtime checks for host opaque values.

Files:
- `src/nicole/runtime.py`
- `tests/test_runtime.py`

Tests:
- Runtime accepts opaque wrapper values whose canonical name matches the expected type.
- Runtime rejects opaque values with mismatched canonical names.
- Runtime supports opaque values in `List<T>`, `Result<T,E>`, and map values.
- Keep equality/inequality runtime checks defensive only (checker remains primary enforcement).
- Preserve existing runtime behavior for non-opaque types.

Expected result:
Runtime can transport and validate opaque values with nominal identity.

Risks:
- Structural matching instead of nominal matching.
- Breaking current runtime validation semantics.

Notes:
No lifecycle/ownership/finalizer behavior is introduced.

---

## Phase 5 — Pipeline and integration

Status: pending

Purpose:
Validate end-to-end behavior through parse/resolve/check/ABI/runtime boundaries with host opaque types.

Files:
- `src/nicole/pipeline.py`
- `tests/test_pipeline.py`
- `tests/test_runtime.py`

Tests:
- End-to-end host word + export paths using declared opaque types.
- End-to-end rejection paths for undeclared opaque types.
- Regression checks for existing export/ABI/effect behavior.

Expected result:
Feature works across the full NicolePy pipeline with isolated, coherent behavior.

Risks:
- Hidden coupling between checker and runtime assumptions.
- Integration-only failures not visible in unit phases.

Notes:
Keep this phase integration-focused; no broad refactor.

---

## Phase 6 — Documentation and final coverage

Status: pending

Purpose:
Publish migration alignment and complete final spec-facing coverage.

Files:
- `README.md`
- `docs/*` (only relevant aligned docs)
- `tests/*` (final missing coverage only)

Tests:
- Final invalid examples aligned with scoped feature constraints.
- Final regression run confirming preserved legacy passing behavior.

Expected result:
NicolePy documents and test suite reflect alignment to `v0.2.0-host-opaque-types`.

Risks:
- Documenting behavior not fully implemented.
- Adding non-spec features during cleanup.

Notes:
Documentation updates happen after implementation behavior is stable.

---

## Progress update rules

After each completed phase:

1. Change phase state:
   pending -> in_progress -> completed

2. Append update block:

### Update YYYY-MM-DD HH:MM

Phase:
...

Changes:
...

Tests added:
...

Tests passing:
...

Unexpected findings:
...

Follow-up actions:
...

3. Never rewrite previous updates.

4. Append only.

---

## Completion criteria

- All six phases are in `completed` status.
- Checker enforces all statically provable constraints for host opaque types.
- Runtime provides nominal opaque representation and defensive runtime validation.
- ABI quote prohibition remains intact.
- Map key restriction remains intact.
- End-to-end tests cover success and failure paths for declared vs undeclared opaque types.
- Documentation states alignment with `v0.2.0-host-opaque-types` and matches implemented behavior.
- No undeclared host.* type can cross any ABI boundary.

### Update 2026-05-23 07:48

Phase:
Phase 1 — ABI opaque type registry

Changes:
- Added `HostOpaqueType` with canonical `host.*` name validation.
- Added immutable opaque type registry to `HostContract` (`opaque_types`).
- Extended `host_contract_from_words(...)` with optional `opaque_types=` while preserving existing host-word behavior.
- Kept ABI signature validation behavior unchanged.

Tests added:
- `tests/test_host_abi.py`
- `test_host_contract_accepts_declared_host_io_file_handle`
- `test_host_contract_accepts_declared_host_net_tcp_socket`
- `test_host_contract_rejects_non_canonical_opaque_type_name`
- `test_host_contract_rejects_duplicate_opaque_type_declarations`
- `test_host_contract_has_no_opaque_type_aliasing_mechanism`
- `test_host_word_contract_behavior_remains_unchanged_with_opaque_registry`
- `tests/test_pipeline.py`
- `test_pipeline_accepts_host_contract_with_declared_opaque_types_in_phase1`

Tests passing:
- `python -m pytest -q` passed (`645 passed`)

Unexpected findings:
- None.

Follow-up actions:
Proceed to Phase 2 — ABI signature validation

### Update 2026-05-23 08:07

Phase:
Phase 2 — ABI signature validation

Changes:
- Added declared-opaque ABI admission context to host ABI signature validation without changing checker wiring.
- Accepted declared `host.*` opaque types in host-word and export ABI signature validation paths.
- Rejected undeclared `host.*` opaque types in ABI-visible signatures.
- Preserved quote and dirty quote ABI prohibition and map key restrictions.
- Kept checker/runtime/parser behavior unchanged.

Tests added:
- `tests/test_host_abi.py`
- `test_host_word_signature_accepts_declared_host_opaque_type`
- `test_host_word_signature_rejects_undeclared_host_opaque_type`
- `test_host_word_signature_accepts_map_value_declared_host_opaque_type`
- `test_host_word_signature_rejects_map_key_host_opaque_type_even_if_declared`
- `test_host_word_signature_rejects_dirty_quote_unchanged`
- `test_host_word_signature_rejects_unknown_nominal_type_foo`
- `test_export_signature_accepts_declared_host_opaque_type`
- `test_export_signature_rejects_undeclared_host_opaque_type`
- `test_export_signature_accepts_map_value_declared_host_opaque_type`
- `test_export_signature_rejects_map_key_host_opaque_type_even_if_declared`
- `test_export_signature_rejects_quote_unchanged`
- `test_export_signature_rejects_dirty_quote_unchanged`
- `test_host_and_export_abi_behavior_is_consistent_for_declared_and_undeclared`
- `tests/test_pipeline.py`
- `test_declared_opaque_registry_does_not_activate_checker_support`

Tests passing:
- `.venv/bin/python -m pytest -q` passed (`663 passed`)

Unexpected findings:
- None.

Follow-up actions:
Proceed to post-Phase 2 audit

### Update 2026-05-23 08:11

Phase:
Phase 2 — corrective integration

Changes:
- Wired `analyze_program(...)` to pass `effective_host_contract` into `collect_exports(...)`.
- Kept ABI rules unchanged and limited the change to canonical pipeline integration.
- Added pipeline-level integration coverage for declared and undeclared opaque export behavior through the public entrypoint.

Tests added:
- `tests/test_pipeline.py`
- `test_pipeline_wires_declared_opaque_types_into_export_collection`
- `test_pipeline_export_rejects_undeclared_opaque_type_when_checker_is_bypassed`

Tests passing:
- `.venv/bin/python -m pytest -q` passed (`665 passed`)

Unexpected findings:
- None.

Follow-up actions:
Ready for post-correction audit

### Update 2026-05-23 08:25

Phase:
Phase 3 — Checker support

Changes:
- Wired declared opaque type names into checker entrypoints (`check_program`/`check`) and pipeline analysis path.
- Added checker-local host opaque type admission in `_validate_language_type_v1(...)` using declared membership only.
- Added dedicated checker rejection for undeclared `host.*` types.
- Preserved map key restriction and existing shared ABI validator behavior (`validate_type_v1(...)` unchanged).
- Added static checker rejection for `=` and `!=` on declared opaque operands.
- Kept runtime behavior unchanged.

Tests added:
- `tests/test_checker.py`
- `test_checker_accepts_declared_opaque_type_in_word_signature`
- `test_checker_accepts_declared_opaque_type_in_local_declaration`
- `test_checker_accepts_declared_opaque_type_stack_flow`
- `test_checker_accepts_declared_opaque_type_in_list`
- `test_checker_accepts_declared_opaque_type_in_result_value`
- `test_checker_accepts_declared_opaque_type_in_result_error`
- `test_checker_accepts_declared_opaque_type_in_quotation_signature`
- `test_checker_accepts_declared_opaque_type_in_map_string_value`
- `test_checker_accepts_declared_opaque_type_in_map_int_value`
- `test_checker_accepts_declared_opaque_type_in_map_bool_value`
- `test_checker_rejects_undeclared_host_opaque_type`
- `test_checker_rejects_declared_opaque_type_as_map_key`
- `test_checker_rejects_equality_on_declared_opaque_type`
- `tests/test_pipeline.py`
- `test_pipeline_checker_accepts_declared_opaque_types_from_host_contract`
- `test_pipeline_checker_rejects_undeclared_opaque_types`

Tests passing:
- `.venv/bin/python -m pytest -q` passed (`680 passed`)

Unexpected findings:
- None.

Follow-up actions:
Proceed to post-Phase 3 audit

### Update 2026-05-23 08:36

Phase:
Phase 4

Changes:
- Added `RuntimeOpaqueValue` runtime wrapper with explicit nominal `type_name` and opaque `payload`.
- Added runtime host-opaque matching path in `_matches_type_name(...)` for `host.*` names.
- Enforced nominal opaque identity matching (`expected type name == wrapper.type_name`) without payload-type matching or duck typing.
- Added runtime defensive guard in `_execute_operator(...)` to reject `=` and `!=` on opaque operands with a dedicated error.
- Kept checker, ABI, parser, resolver, lexer, and pipeline behavior unchanged.

Tests added:
- `tests/test_runtime.py`
- `test_runtime_accepts_host_opaque_wrapper_for_host_input_output`
- `test_runtime_accepts_host_opaque_wrapper_for_export_input_output`
- `test_runtime_accepts_host_opaque_wrapper_for_quotation_capture_input_output`
- `test_runtime_accepts_host_opaque_wrapper_in_list`
- `test_runtime_accepts_host_opaque_wrapper_in_result_value`
- `test_runtime_accepts_host_opaque_wrapper_in_result_error`
- `test_runtime_accepts_host_opaque_wrapper_in_map_string_value`
- `test_runtime_accepts_host_opaque_wrapper_in_map_int_value`
- `test_runtime_accepts_host_opaque_wrapper_in_map_bool_value`
- `test_runtime_rejects_host_opaque_wrapper_with_wrong_type_name`
- `test_runtime_rejects_malformed_host_opaque_wrapper`
- `test_runtime_rejects_raw_python_object_for_host_opaque_type`
- `test_runtime_rejects_file_handle_when_tcp_socket_expected`
- `test_runtime_rejects_equality_on_host_opaque_values`
- `test_runtime_rejects_inequality_on_host_opaque_values`

Tests passing:
- `.venv/bin/python -m pytest -q tests/test_runtime.py` passed (`197 passed`)
- `.venv/bin/python -m pytest -q` passed (`695 passed`)

Unexpected findings:
- None.

Follow-up actions:
Proceed to post-Phase 4 audit
