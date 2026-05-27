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
- `IdentifierNode.name` preserves the source lexeme written in module code
- canonical export publication uses `@module.word`
- runtime export lookup uses canonical/module-qualified identities

Known deferred gaps after B5C2/B5D freeze:

- `runtime.py` remains legacy-centric and still dispatches host bindings by `host.*`
- `host_abi.py` remains legacy-centric
- pipeline still bridges canonical `@host.*` source identities to legacy `host.*` runtime identities
- runtime host identity migration is complete through B5C2; Python ABI migration is deferred

B5D freeze scope (Python host ABI boundary only):

- preserve runtime behavior and preserve Python ABI behavior
- preserve resolver/runtime split identities for imported host calls:
- `ResolutionInfo.qualified_name == "@host.*"`
- `ResolutionInfo.host_binding_name == "host.*"`
- `IdentifierNode.name` remains source lexeme (no legacy mutation in resolver)
- preserve `ResolutionInfo.host_binding_name is None` for non-host symbols
- preserve legacy Python ABI/runtime boundary identities:
- `RuntimeHostBindings` keys remain `host.*`
- `HostWord` names remain `host.*`
- `HostOpaqueType` names remain `host.*`
- `RuntimeOpaqueValue.type_name` remains `host.*`
- preserve canonical source export identity `@module.word`
- preserve explicit source-to-legacy bridge in pipeline (`SourceHostContract` -> `HostContract`)
- B5D does not migrate Python ABI naming, does not migrate runtime opaque identity, and does not change runtime host diagnostics/traces

B6 freeze scope (user compile/run facade):

- `NicoleCompiler` and `NicoleApplication` are the recommended user-facing Python workflow
- compile inputs remain explicit (`.nic` file, directory, or mixed path list)
- execution remains explicit by export name (for example `@app.main`)
- no implicit entrypoint behavior is introduced
- no VM/session/debugger API is introduced
- B6 does not reopen B5 runtime identity or Python ABI boundary decisions

Nicole specification remains the only language source of truth.
