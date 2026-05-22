# NicolePy Spec Target

Current target specification:

- spec repo: `/data/data/com.termux/files/home/Sources/nicole/nicole_language_docs_seed`
- tag: `v0.1.0-modules-freeze`
- commit: `08706edd315e64c22b47e69b4121a0f0f04e7a9f`

Target summary:

- user-defined words are module-contained
- imports are top-level declarations
- exports are module-local declarations written as `export : word`
- canonical host-visible export names are `@module.word`
- legacy flat export syntax is not public behavior

Current implementation state against this target:

- parser supports module/import/include/export declaration syntax
- signature collection, resolver, checker, pipeline, host ABI, and runtime are module-aware
- canonical export publication uses `@module.word`
- runtime export lookup uses canonical/module-qualified identities

Known deferred gaps outside the core Phase 1-4 target:

- full import-graph cycle rejection still depends on complete compilation-unit/module-loading graph information
- visible-root collision diagnostics remain limited to currently representable alias-collision paths

Nicole specification remains the only language source of truth.
