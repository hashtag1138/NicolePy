from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.ast_nodes import IdentifierNode, ModuleDeclaration, WordDefNode
from nicole.checker import CheckerError
from nicole.host_abi import HostABIError, HostEffect, HostWord, host_contract_from_words
from nicole.pipeline import CheckedProgram, analyze_program
from nicole.resolver import ResolutionError
from nicole.parser import Parser
from nicole.lexer import lex
from nicole.symbols import SymbolError


def _parse_source(source: str):
    return Parser(lex(source)).parse()


def _get_module_word(program, *, module_name: str, word_name: str) -> WordDefNode:
    for declaration in program.declarations:
        if not isinstance(declaration, ModuleDeclaration):
            continue
        if ".".join(declaration.name.parts) != module_name:
            continue
        for item in declaration.items:
            if isinstance(item, WordDefNode) and item.name == word_name:
                return item
    raise AssertionError(f"word '{word_name}' not found in module '@{module_name}'")


def _signature_from_source(source: str, *, module_name: str, word_name: str):
    program = _parse_source(source)
    return _get_module_word(program, module_name=module_name, word_name=word_name).signature


def test_pipeline_accepts_module_program_without_exports() -> None:
    result = analyze_program(
        "module @app\n"
        "  : main { -- n:Int }\n"
        "    1\n"
        "  ;\n"
        "end-module\n"
    )

    assert isinstance(result, CheckedProgram)
    assert dict(result.export_contract.words) == {}


def test_pipeline_resolves_same_module_short_name() -> None:
    result = analyze_program(
        "module @app\n"
        "  : helper { -- }\n"
        "  ;\n"
        "  : run { -- }\n"
        "    helper\n"
        "  ;\n"
        "end-module\n"
    )

    call = _get_module_word(result.program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "app"
    assert call.resolution.resolved_symbol.name == "helper"


def test_pipeline_resolves_external_qualified_reference_with_import() -> None:
    result = analyze_program(
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

    call = _get_module_word(result.program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "math"


def test_pipeline_rejects_external_qualified_reference_without_import() -> None:
    with pytest.raises(ResolutionError, match="unresolved name"):
        analyze_program(
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


def test_pipeline_resolves_alias_qualified_reference() -> None:
    result = analyze_program(
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

    call = _get_module_word(result.program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "math"


def test_pipeline_resolves_imported_word_alias() -> None:
    result = analyze_program(
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

    call = _get_module_word(result.program, module_name="app", word_name="run").body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "math"
    assert call.resolution.resolved_symbol.name == "add"


def test_pipeline_accepts_builtins_and_imports_together() -> None:
    result = analyze_program(
        "module @math\n"
        "  : inc { n:Int -- out:Int }\n"
        "    n 1 +\n"
        "  ;\n"
        "end-module\n"
        "import @math\n"
        "module @app\n"
        "  : run { xs:List<Int> n:Int -- ok:Bool out:Int }\n"
        "    xs list.is-empty\n"
        "    n @math.inc\n"
        "  ;\n"
        "end-module\n"
    )

    assert isinstance(result, CheckedProgram)


def test_pipeline_accepts_host_calls_with_imports() -> None:
    host_signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n",
        module_name="sig",
        word_name="hostsig",
    )
    host_contract = host_contract_from_words([
        HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)
    ])

    result = analyze_program(
        "module @util\n"
        "  : normalize { msg:String -- out:String }\n"
        "    msg\n"
        "  ;\n"
        "end-module\n"
        "import @util\n"
        "module @app\n"
        "  : send { msg:String -- }\n"
        "    msg @util.normalize host.log\n"
        "  ;\n"
        "end-module\n",
        host_contract=host_contract,
    )

    send = _get_module_word(result.program, module_name="app", word_name="send")
    import_call = send.body.items[1]
    host_call = send.body.items[2]
    assert isinstance(import_call, IdentifierNode)
    assert isinstance(host_call, IdentifierNode)
    assert import_call.resolution.resolved_symbol is not None
    assert import_call.resolution.resolved_symbol.module == "util"
    assert host_call.resolution.owner_scope == "host"


def test_pipeline_preserves_same_name_cross_module_words() -> None:
    result = analyze_program(
        "module @b\n"
        "  : run { n:Int -- n2:Int }\n"
        "    n\n"
        "  ;\n"
        "end-module\n"
        "import @b\n"
        "module @a\n"
        "  : run { n:Int -- n2:Int }\n"
        "    n @b.run\n"
        "  ;\n"
        "end-module\n"
    )

    runs = result.symbols.words["run"]
    assert len(runs) == 2
    assert {symbol.module for symbol in runs} == {"a", "b"}

    call = _get_module_word(result.program, module_name="a", word_name="run").body.items[1]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "b"


def test_pipeline_rejects_pure_cross_module_call_to_dirty_same_name_word() -> None:
    host_signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n",
        module_name="sig",
        word_name="hostsig",
    )
    host_contract = host_contract_from_words([
        HostWord(name="host.log", signature=host_signature, effect=HostEffect.DIRTY)
    ])

    with pytest.raises(CheckerError, match=r"inferred dirty.*missing dirty annotation"):
        analyze_program(
            "module @b\n"
            "  dirty : run { msg:String -- }\n"
            "    msg host.log\n"
            "  ;\n"
            "end-module\n"
            "import @b\n"
            "module @a\n"
            "  : run { msg:String -- }\n"
            "    msg @b.run\n"
            "  ;\n"
            "end-module\n",
            host_contract=host_contract,
        )


def test_pipeline_marks_true_same_module_self_tail_call() -> None:
    result = analyze_program(
        "module @app\n"
        "  : loop { n:Int -- n2:Int }\n"
        "    n loop\n"
        "  ;\n"
        "end-module\n"
    )

    loop = _get_module_word(result.program, module_name="app", word_name="loop")
    call = loop.body.items[1]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.is_self_tail_call is True


def test_pipeline_does_not_mark_cross_module_same_name_tail_call_as_self() -> None:
    result = analyze_program(
        "module @b\n"
        "  : loop { n:Int -- n2:Int }\n"
        "    n\n"
        "  ;\n"
        "end-module\n"
        "import @b\n"
        "module @a\n"
        "  : loop { n:Int -- n2:Int }\n"
        "    n @b.loop\n"
        "  ;\n"
        "end-module\n"
    )

    loop = _get_module_word(result.program, module_name="a", word_name="loop")
    call = loop.body.items[1]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.is_self_tail_call is False
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.module == "b"


def test_pipeline_exposes_canonical_export_contract() -> None:
    result = analyze_program(
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    42\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )

    assert "@app.run" in result.export_contract.words
    export_word = result.export_contract.words["@app.run"]
    assert export_word.export_name == "@app.run"
    assert export_word.internal_name == "@app.run"


def test_pipeline_export_survives_full_collection_and_abi_path() -> None:
    result = analyze_program(
        "module @app\n"
        "  : run { msg:String -- }\n"
        "    msg drop\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )

    assert list(result.export_contract.words.keys()) == ["@app.run"]
    assert result.export_contract.words["@app.run"].signature is result.symbols.words["run"][0].signature


def test_pipeline_valid_export_coexists_with_import_aliases() -> None:
    result = analyze_program(
        "module @core\n"
        "  : run { -- n:Int }\n"
        "    7\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
        "import @core as c\n"
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    c.run\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )

    assert set(result.export_contract.words.keys()) == {"@core.run", "@app.run"}


def test_pipeline_invalid_export_target_is_compile_time_error() -> None:
    with pytest.raises(SymbolError, match="export target does not exist"):
        analyze_program(
            "module @app\n"
            "  export : missing\n"
            "end-module\n"
        )


def test_pipeline_rejects_export_of_subword() -> None:
    with pytest.raises(SymbolError, match="module-level"):
        analyze_program(
            "module @app\n"
            "  : parent { -- }\n"
            "    : child { -- }\n"
            "    ;\n"
            "  ;\n"
            "  export : child\n"
            "end-module\n"
        )


def test_pipeline_export_abi_validation_is_preserved() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "module @app\n"
            "  : run { -- q:Quote<{ | -- }> }\n"
            "    :[ | -- | ;]\n"
            "  ;\n"
            "  export : run\n"
            "end-module\n"
        )
