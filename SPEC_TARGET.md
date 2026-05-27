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

B5A freeze scope (bridge visibility only):

- preserve runtime behavior and preserve Python ABI behavior
- preserve resolver bridge split for imported host calls:
- `ResolutionInfo.qualified_name == "@host.*"`
- `ResolutionInfo.host_binding_name == "host.*"`
- `IdentifierNode.name == "host.*"` (runtime compatibility mutation remains intentional)
- preserve `ResolutionInfo.host_binding_name is None` for non-host symbols
- preserve legacy runtime/ABI identities:
- `RuntimeHostBindings` keys remain `host.*`
- `HostWord` names remain `host.*`
- `HostOpaqueType` names remain `host.*`
- `RuntimeOpaqueValue.type_name` remains `host.*`
- preserve canonical source export identity `@module.word`
- B5A does not migrate runtime dispatch, does not canonicalize runtime naming, and does not remove bridge fields

Nicole specification remains the only language source of truth.
