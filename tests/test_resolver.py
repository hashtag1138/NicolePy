from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.errors import DiagnosticPhase
from nicole.ast_nodes import IdentifierNode, ModuleDeclaration, WordDefNode
from nicole.host_abi import BindingAvailability, HostEffect, HostWord, host_contract_from_words
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.resolver import ResolutionError, resolve
from nicole.signature_collector import collect_signatures
from nicole.standard_symbols import with_standard_symbols
from nicole.symbols import SymbolError


def resolve_source(source: str, *, with_builtins: bool = False):
    program = Parser(lex(source)).parse()
    symbols = collect_signatures(program)
    if with_builtins:
        symbols = with_standard_symbols(symbols)
    return resolve(program, symbols)


def resolve_source_with_host_contract(source: str, host_words):
    program = Parser(lex(source)).parse()
    symbols = collect_signatures(program)
    contract = host_contract_from_words(host_words)
    return resolve(program, symbols, host_contract=contract)


def signature_from_source(source: str, *, module_name: str, word_name: str):
    program = Parser(lex(source)).parse()
    return get_module_word(program, module_name=module_name, word_name=word_name).signature


def get_module_word(program, *, module_name: str, word_name: str) -> WordDefNode:
    for declaration in program.declarations:
        if not isinstance(declaration, ModuleDeclaration):
            continue
        if ".".join(declaration.name.parts) != module_name:
            continue
        for item in declaration.items:
            if isinstance(item, WordDefNode) and item.name == word_name:
                return item
    raise AssertionError(f"word '{word_name}' not found in module '@{module_name}'")


def test_resolves_same_module_short_name() -> None:
    program = resolve_source(
        "module @app\n"
        "  : helper { -- }\n"
        "  ;\n"
        "  : run { -- }\n"
        "    helper\n"
        "  ;\n"
        "end-module\n"
    )

    call = get_module_word(program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "app"
    assert call.resolution.resolved_symbol.name == "helper"


def test_resolves_same_module_qualified_reference_without_import() -> None:
    program = resolve_source(
        "module @app\n"
        "  : helper { -- }\n"
        "  ;\n"
        "  : run { -- }\n"
        "    @app.helper\n"
        "  ;\n"
        "end-module\n"
    )

    call = get_module_word(program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "app"
    assert call.resolution.resolved_symbol.name == "helper"


def test_resolves_external_qualified_reference_with_matching_import() -> None:
    program = resolve_source(
        "module @math\n"
        "  : add { -- }\n"
        "  ;\n"
        "end-module\n"
        "import @math\n"
        "module @app\n"
        "  : run { -- }\n"
        "    @math.add\n"
        "  ;\n"
        "end-module\n"
    )

    call = get_module_word(program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "math"
    assert call.resolution.resolved_symbol.name == "add"


def test_rejects_external_qualified_reference_without_import() -> None:
    with pytest.raises(ResolutionError, match="unresolved name"):
        resolve_source(
            "module @math\n"
            "  : add { -- }\n"
            "  ;\n"
            "end-module\n"
            "module @app\n"
            "  : run { -- }\n"
            "    @math.add\n"
            "  ;\n"
            "end-module\n"
        )


def test_resolves_module_import_alias_qualified_reference() -> None:
    program = resolve_source(
        "module @math\n"
        "  : add { -- }\n"
        "  ;\n"
        "end-module\n"
        "import @math as m\n"
        "module @app\n"
        "  : run { -- }\n"
        "    m.add\n"
        "  ;\n"
        "end-module\n"
    )

    call = get_module_word(program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "math"
    assert call.resolution.resolved_symbol.name == "add"


def test_resolves_direct_imported_word_alias() -> None:
    program = resolve_source(
        "module @math\n"
        "  : add { -- }\n"
        "  ;\n"
        "end-module\n"
        "import @math.add as add\n"
        "module @app\n"
        "  : run { -- }\n"
        "    add\n"
        "  ;\n"
        "end-module\n"
    )

    call = get_module_word(program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "math"
    assert call.resolution.resolved_symbol.name == "add"


def test_rejects_missing_alias_usage() -> None:
    with pytest.raises(ResolutionError, match="unresolved name"):
        resolve_source(
            "module @math\n"
            "  : add { -- }\n"
            "  ;\n"
            "end-module\n"
            "import @math\n"
            "module @app\n"
            "  : run { -- }\n"
            "    m.add\n"
            "  ;\n"
            "end-module\n"
        )


def test_rejects_cross_module_short_name_fallback() -> None:
    with pytest.raises(ResolutionError, match="unresolved name"):
        resolve_source(
            "module @math\n"
            "  : add { -- }\n"
            "  ;\n"
            "end-module\n"
            "module @app\n"
            "  : run { -- }\n"
            "    add\n"
            "  ;\n"
            "end-module\n"
        )


def test_local_lexical_names_resolve_before_imported_aliases() -> None:
    program = resolve_source(
        "module @math\n"
        "  : x { -- }\n"
        "  ;\n"
        "end-module\n"
        "import @math.x as x\n"
        "module @app\n"
        "  : run { x:Int -- }\n"
        "    x\n"
        "  ;\n"
        "end-module\n"
    )

    call = get_module_word(program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.qualified_name == "local:x"
    assert call.resolution.resolved_symbol is None


def test_builtin_resolution_remains_stable() -> None:
    program = resolve_source(
        "module @app\n"
        "  : main { xs:List<Int> -- r:Result<Int,ListError> }\n"
        "    xs 0 list.get\n"
        "  ;\n"
        "end-module\n",
        with_builtins=True,
    )

    builtin_ref = get_module_word(program, module_name="app", word_name="main").body.items[2]
    assert isinstance(builtin_ref, IdentifierNode)
    assert builtin_ref.resolution.resolved_symbol is not None
    assert builtin_ref.resolution.resolved_symbol.name == "list.get"
    assert builtin_ref.resolution.resolved_symbol.source.name == "BUILTIN"


def test_host_resolution_remains_stable() -> None:
    signature = signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n",
        module_name="sig",
        word_name="hostsig",
    )
    program = resolve_source_with_host_contract(
        "module @app\n"
        "  : log { msg:String -- }\n"
        "    msg host.log\n"
        "  ;\n"
        "end-module\n",
        [HostWord(name="host.log", signature=signature, effect=HostEffect.PURE)],
    )

    host_ref = get_module_word(program, module_name="app", word_name="log").body.items[1]
    assert isinstance(host_ref, IdentifierNode)
    assert host_ref.resolution.owner_scope == "host"
    assert host_ref.resolution.qualified_name == "host.log"
    assert host_ref.resolution.resolved_symbol is not None


def test_required_host_resolution_remains_stable() -> None:
    signature = signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n",
        module_name="sig",
        word_name="hostsig",
    )
    program = resolve_source_with_host_contract(
        "module @app\n"
        "  : log { msg:String -- }\n"
        "    msg host.log\n"
        "  ;\n"
        "end-module\n",
        [
            HostWord(
                name="host.log",
                signature=signature,
                availability=BindingAvailability.REQUIRED,
                effect=HostEffect.PURE,
            )
        ],
    )

    host_ref = get_module_word(program, module_name="app", word_name="log").body.items[1]
    assert isinstance(host_ref, IdentifierNode)
    assert host_ref.resolution.owner_scope == "host"
    assert host_ref.resolution.qualified_name == "host.log"


def test_rejects_reserved_root_import_alias() -> None:
    with pytest.raises(SymbolError, match="cannot use reserved root as import alias: list"):
        resolve_source(
            "import @math as list\n"
            "module @app\n"
            "end-module\n"
        )


def test_rejects_duplicate_import_alias() -> None:
    with pytest.raises(SymbolError, match="duplicate import alias: m"):
        resolve_source(
            "import @math as m\n"
            "import @tools as m\n"
            "module @app\n"
            "end-module\n"
        )


def test_symbol_error_exposes_structured_diagnostic() -> None:
    with pytest.raises(SymbolError) as exc_info:
        resolve_source(
            "import @math as list\n"
            "module @app\n"
            "end-module\n"
        )

    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.SYMBOLS
    assert error.diagnostic.code == "SYMBOLS_RESERVED_IMPORT_ALIAS"
    assert error.message == "cannot use reserved root as import alias: list"
    assert error.line == error.diagnostic.span.line
    assert error.column == error.diagnostic.span.column


def test_resolver_unresolved_name_exposes_structured_diagnostic() -> None:
    source = (
        "module @app\n"
        "  : run { -- }\n"
        "    missing\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(ResolutionError) as exc_info:
        resolve_source(source)

    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.RESOLVER
    assert error.diagnostic.code == "RESOLVER_UNRESOLVED_NAME"
    assert error.message == "unresolved name"
    assert error.diagnostic.span is not None
    assert error.line == error.diagnostic.span.line
    assert error.column == error.diagnostic.span.column


def test_resolver_host_contract_required_exposes_structured_diagnostic() -> None:
    with pytest.raises(ResolutionError) as exc_info:
        resolve_source(
            "module @app\n"
            "  : run { msg:String -- }\n"
            "    msg host.log\n"
            "  ;\n"
            "end-module\n"
        )

    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.RESOLVER
    assert error.diagnostic.code == "RESOLVER_HOST_CONTRACT_REQUIRED"
    assert error.message == "host contract required for host.* reference"


def test_resolver_unknown_host_word_exposes_structured_diagnostic() -> None:
    hostsig = signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n",
        module_name="sig",
        word_name="hostsig",
    )
    with pytest.raises(ResolutionError) as exc_info:
        resolve_source_with_host_contract(
            "module @app\n"
            "  : run { msg:String -- }\n"
            "    msg host.log\n"
            "  ;\n"
            "end-module\n",
            [HostWord(name="host.print", signature=hostsig, effect=HostEffect.PURE)],
        )

    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.RESOLVER
    assert error.diagnostic.code == "RESOLVER_UNKNOWN_HOST_WORD"
    assert error.message == "unknown host word"


def test_resolver_optional_host_word_direct_call_exposes_structured_diagnostic() -> None:
    hostsig = signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n",
        module_name="sig",
        word_name="hostsig",
    )
    with pytest.raises(ResolutionError) as exc_info:
        resolve_source_with_host_contract(
            "module @app\n"
            "  : run { msg:String -- }\n"
            "    msg host.log\n"
            "  ;\n"
            "end-module\n",
            [
                HostWord(
                    name="host.log",
                    signature=hostsig,
                    availability=BindingAvailability.OPTIONAL,
                    effect=HostEffect.PURE,
                )
            ],
        )

    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.RESOLVER
    assert error.diagnostic.code == "RESOLVER_OPTIONAL_HOST_WORD_DIRECT_CALL"
    assert error.message == "optional host word cannot be called directly in v1"
