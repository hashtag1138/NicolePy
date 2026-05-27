# NicolePy Spec Target

Current target specification:

- spec repo: `/data/data/com.termux/files/home/Sources/nicole/nicole_language_docs_seed`
- tag: `v0.3.1-source-visible-host-abi-freeze`
- commit: `a8756807fc8bd8294d7fc44c146967ec270bedbf`

Target summary:

- user-defined words are module-contained
- imports are top-level declarations
- exports are module-local declarations written as `export : word`
- canonical host-visible export names are `@module.word`
- `module @host` declares the source-visible host ABI
- `require` introduces importable host capabilities
- `opaque` introduces importable host opaque types
- grouped imports are semantic sugar for explicit imports
- direct source calls `host.*` are invalid
- canonical source-visible host identities are `@host.*`

Current implementation state against this target:

- parser preserves canonical `@host.*` type names in `TypeNode.name`
- signature collection consolidates `module @host` fragments into a canonical `SourceHostContract`
- grouped imports are desugared semantically and preserve symbol category
- resolver rejects direct source `host.*` and resolves imported host capabilities canonically
- checker accepts canonical imported host opaque types in type position and rejects host capability-as-type
- `ResolutionInfo.qualified_name` is canonical `@host.*`
- `ResolutionInfo.host_binding_name` keeps the narrow legacy runtime bridge `host.*`
- canonical export publication uses `@module.word`
- runtime export lookup uses canonical/module-qualified identities

Known deferred gaps after B4:

- `runtime.py` remains legacy-centric and still dispatches host bindings by `host.*`
- `host_abi.py` remains legacy-centric
- pipeline still bridges canonical `@host.*` source identities to legacy `host.*` runtime identities
- full runtime alignment is the planned B5 phase

Nicole specification remains the only language source of truth.
