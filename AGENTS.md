# AGENTS.md

This repository implements Nicole in Python.

Do not redefine the language here.
Do not correct the specification silently.
Do not optimize before the conformant path exists.
Do not reintroduce same-name multiple definitions.
Do not describe signature inputs as an initial local stack.
Do not document quotations with `]` alone; value quotations close with `;]`.
Do not document duplicate local names in one frame as valid.
Do not document `list.map`, `list.fold`, or `list.reduce` as requiring quotations with `captures == []`.
Do not describe `host.*` or `export` as fully implemented ABI features while the contract remains partial.
Do not document bare `/` as a v1 arithmetic operator.
Do not document implicit `Int`/`Float` coercion.
Do not document directly called optional `host.*` words as valid in v1.
Do document `nicole.pipeline.analyze_program(...)` as the canonical static analysis path when describing the current repository.
Do document `HostContract` and `ExportContract` as minimal static ABI contracts, not as a complete runtime ABI.
Do document `checker.py` as the live checker.

Priority order:

1. Lexer
2. Parser
3. Signature collection
4. Name resolution
5. Type checking
6. Simple IR
7. Interpreter
8. Host integration
9. Conformance tests

If code and spec diverge, the spec wins.
