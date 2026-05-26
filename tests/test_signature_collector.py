from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.ast_nodes import BlockNode, ProgramNode, SignatureNode, WordDefNode
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.signature_collector import collect_semantic_model, collect_signatures
from nicole.symbols import ImportMetadata, SymbolCategory, SymbolError, WordSymbol
from nicole.tokens import SourceSpan


def parse_source(source: str):
    return Parser(lex(source)).parse()


def _span() -> SourceSpan:
    return SourceSpan(line=1, column=1, offset=0)


def test_does_not_collect_legacy_top_level_words_when_declarations_are_empty() -> None:
    legacy_word = WordDefNode(
        span=_span(),
        name="legacy",
        signature=SignatureNode(span=_span()),
        body=BlockNode(span=_span()),
    )
    program = ProgramNode(span=_span(), words=(legacy_word,), declarations=())

    table = collect_signatures(program)

    assert "legacy" not in table.words
    assert table.words == {}


def test_collects_words_from_module_items() -> None:
    program = parse_source(
        "module @app\n"
        "  : run { -- }\n"
        "  ;\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert "run" in table.words
    symbol = table.words["run"][0]
    assert isinstance(symbol, WordSymbol)
    assert symbol.module == "app"
    assert symbol.owner is None


def test_nested_subword_collection_preserves_module_ownership() -> None:
    program = parse_source(
        "module @app\n"
        "  : parent { -- }\n"
        "    : child { -- }\n"
        "    ;\n"
        "  ;\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert "parent" in table.words
    assert "child" in table.words
    child_symbol = table.words["child"][0]
    assert child_symbol.module == "app"
    assert child_symbol.owner == "parent"
    assert child_symbol.qualified_name == "parent.child"


def test_same_subword_name_is_allowed_under_different_parents_in_same_module() -> None:
    program = parse_source(
        "module @app\n"
        "  : invoice { -- }\n"
        "    : total { -- }\n"
        "    ;\n"
        "  ;\n"
        "  : report { -- }\n"
        "    : total { -- }\n"
        "    ;\n"
        "  ;\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert "total" in table.words
    assert len(table.words["total"]) == 2
    assert {symbol.owner for symbol in table.words["total"]} == {"invoice", "report"}
    assert {symbol.module for symbol in table.words["total"]} == {"app"}


def test_duplicate_subword_name_is_rejected_under_same_parent() -> None:
    program = parse_source(
        "module @app\n"
        "  : invoice { -- }\n"
        "    : total { -- }\n"
        "    ;\n"
        "    : total { -- }\n"
        "    ;\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(SymbolError, match="duplicate visible name: total"):
        collect_signatures(program)


def test_same_short_word_is_allowed_in_different_modules() -> None:
    program = parse_source(
        "module @app\n"
        "  : run { -- }\n"
        "  ;\n"
        "end-module\n"
        "module @tools\n"
        "  : run { -- }\n"
        "  ;\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert "run" in table.words
    assert len(table.words["run"]) == 2
    assert {symbol.module for symbol in table.words["run"]} == {"app", "tools"}


def test_duplicate_short_word_is_rejected_in_same_module() -> None:
    program = parse_source(
        "module @app\n"
        "  : run { -- }\n"
        "  ;\n"
        "  : run { -- }\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(SymbolError, match="duplicate visible name: run"):
        collect_signatures(program)


def test_duplicate_module_declaration_is_rejected() -> None:
    program = parse_source(
        "module @app\n"
        "end-module\n"
        "module @app\n"
        "end-module\n"
    )
    with pytest.raises(SymbolError, match="duplicate module declaration: app"):
        collect_signatures(program)


def test_import_declaration_metadata_is_recorded() -> None:
    program = parse_source(
        "module @app\n"
        "  import @math\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert len(table.imports) == 1
    metadata = table.imports[0]
    assert isinstance(metadata, ImportMetadata)
    assert metadata.owner_module == "app"
    assert metadata.target == "math"
    assert metadata.alias is None


def test_import_alias_metadata_is_recorded() -> None:
    program = parse_source(
        "module @app\n"
        "  import @math.utils as u\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert len(table.imports) == 1
    metadata = table.imports[0]
    assert metadata.owner_module == "app"
    assert metadata.target == "math.utils"
    assert metadata.alias == "u"
    assert table.aliases[("app", "u")] is metadata


def test_same_alias_is_allowed_in_different_modules() -> None:
    program = parse_source(
        "module @app\n"
        "  import @math as m\n"
        "end-module\n"
        "module @tools\n"
        "  import @utils as m\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert len(table.imports) == 2
    assert ("app", "m") in table.aliases
    assert ("tools", "m") in table.aliases
    assert table.aliases[("app", "m")].target == "math"
    assert table.aliases[("tools", "m")].target == "utils"


def test_imports_are_recorded_per_owner_module() -> None:
    program = parse_source(
        "module @app\n"
        "  import @math\n"
        "end-module\n"
        "module @tools\n"
        "  import @util\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert {(metadata.owner_module, metadata.target) for metadata in table.imports} == {
        ("app", "math"),
        ("tools", "util"),
    }


def test_grouped_import_with_prefix_alias_is_desugared_into_explicit_imports() -> None:
    program = parse_source(
        "module @app\n"
        "  import @host.io.{ open-file close-file FileHandle } as io\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert len(table.imports) == 3
    assert {(metadata.target, metadata.alias) for metadata in table.imports} == {
        ("host.io.open-file", "io.open-file"),
        ("host.io.close-file", "io.close-file"),
        ("host.io.FileHandle", "io.FileHandle"),
    }
    assert all(metadata.owner_module == "app" for metadata in table.imports)
    assert all(metadata.is_grouped_expansion for metadata in table.imports)
    assert all(metadata.group_parent_target == "host.io" for metadata in table.imports)
    assert {metadata.group_member for metadata in table.imports} == {"open-file", "close-file", "FileHandle"}


def test_grouped_import_with_as_star_desugars_to_short_aliases_only() -> None:
    program = parse_source(
        "module @app\n"
        "  import @host.console.{ log read-line } as *\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert len(table.imports) == 2
    assert {(metadata.target, metadata.alias) for metadata in table.imports} == {
        ("host.console.log", "log"),
        ("host.console.read-line", "read-line"),
    }
    assert all(metadata.is_grouped_expansion for metadata in table.imports)
    assert all(metadata.group_parent_target == "host.console" for metadata in table.imports)
    assert {metadata.group_member for metadata in table.imports} == {"log", "read-line"}


def test_grouped_import_desugaring_applies_to_user_modules_too() -> None:
    program = parse_source(
        "module @app\n"
        "  import @math.ops.{ add sub } as ops\n"
        "end-module\n"
    )
    table = collect_signatures(program)

    assert {(metadata.target, metadata.alias) for metadata in table.imports} == {
        ("math.ops.add", "ops.add"),
        ("math.ops.sub", "ops.sub"),
    }


def test_grouped_import_alias_collision_in_same_module_is_rejected() -> None:
    program = parse_source(
        "module @app\n"
        "  import @math.ops.{ add } as ops\n"
        "  import @tools.ops.{ add } as ops\n"
        "end-module\n"
    )
    with pytest.raises(SymbolError, match="duplicate import alias: ops.add"):
        collect_signatures(program)


def test_grouped_import_alias_can_repeat_in_different_modules() -> None:
    program = parse_source(
        "module @app\n"
        "  import @math.ops.{ add } as ops\n"
        "end-module\n"
        "module @other\n"
        "  import @tools.ops.{ add } as ops\n"
        "end-module\n"
    )
    table = collect_signatures(program)
    assert ("app", "ops.add") in table.aliases
    assert ("other", "ops.add") in table.aliases


@pytest.mark.parametrize("reserved_root", ["list", "map", "result"])
def test_reserved_root_module_name_is_rejected(reserved_root: str) -> None:
    program = parse_source(
        f"module @{reserved_root}\n"
        "end-module\n"
    )
    with pytest.raises(
        SymbolError,
        match=rf"cannot use reserved root as module name: @{reserved_root}",
    ):
        collect_signatures(program)


@pytest.mark.parametrize("reserved_root", ["host", "list", "map", "result"])
def test_reserved_root_alias_is_rejected(reserved_root: str) -> None:
    program = parse_source(
        "module @app\n"
        f"  import @math as {reserved_root}\n"
        "end-module\n"
    )
    with pytest.raises(
        SymbolError,
        match=rf"cannot use reserved root as import alias: {reserved_root}",
    ):
        collect_signatures(program)


def test_collect_semantic_model_preserves_word_category_defaults() -> None:
    model = collect_semantic_model(
        parse_source(
            "module @app\n"
            "  : run { -- }\n"
            "  ;\n"
            "end-module\n"
        )
    )
    symbol = model.symbols.words["run"][0]
    assert symbol.category is SymbolCategory.USER_WORD


def test_collect_semantic_model_collects_host_capability_canonical_name() -> None:
    model = collect_semantic_model(
        parse_source(
            "module @host\n"
            "  require console.log { msg:String -- } dirty\n"
            "end-module\n"
        )
    )
    assert "@host.console.log" in model.source_host_contract.capabilities


def test_collect_semantic_model_collects_host_opaque_canonical_name() -> None:
    model = collect_semantic_model(
        parse_source(
            "module @host\n"
            "  opaque io.FileHandle\n"
            "end-module\n"
        )
    )
    assert "@host.io.FileHandle" in model.source_host_contract.opaque_types


def test_collect_semantic_model_consolidates_multiple_host_fragments() -> None:
    model = collect_semantic_model(
        parse_source(
            "module @host\n"
            "  require console.log { msg:String -- } dirty\n"
            "end-module\n"
            "module @host\n"
            "  opaque io.FileHandle\n"
            "end-module\n"
        )
    )
    assert "@host.console.log" in model.source_host_contract.capabilities
    assert "@host.io.FileHandle" in model.source_host_contract.opaque_types


def test_collect_semantic_model_accepts_identical_host_require_duplicate() -> None:
    model = collect_semantic_model(
        parse_source(
            "module @host\n"
            "  require console.log { msg:String -- } dirty\n"
            "end-module\n"
            "module @host\n"
            "  require console.log { msg:String -- } dirty\n"
            "end-module\n"
        )
    )
    assert len(model.source_host_contract.capabilities) == 1


def test_collect_semantic_model_rejects_divergent_host_require_duplicate() -> None:
    with pytest.raises(SymbolError, match="conflicting host capability declaration: @host.console.log"):
        collect_semantic_model(
            parse_source(
                "module @host\n"
                "  require console.log { msg:String -- } dirty\n"
                "end-module\n"
                "module @host\n"
                "  require console.log { msg:String -- } pure\n"
                "end-module\n"
            )
        )


def test_collect_semantic_model_accepts_identical_host_opaque_duplicate() -> None:
    model = collect_semantic_model(
        parse_source(
            "module @host\n"
            "  opaque io.FileHandle\n"
            "end-module\n"
            "module @host\n"
            "  opaque io.FileHandle\n"
            "end-module\n"
        )
    )
    assert len(model.source_host_contract.opaque_types) == 1


def test_collect_semantic_model_rejects_host_category_collision() -> None:
    with pytest.raises(SymbolError, match="host symbol category conflict: @host.io.FileHandle"):
        collect_semantic_model(
            parse_source(
                "module @host\n"
                "  require io.FileHandle { -- } pure\n"
                "end-module\n"
                "module @host\n"
                "  opaque io.FileHandle\n"
                "end-module\n"
            )
        )
