from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.ast_nodes import (
    BlockNode,
    CaseNode,
    ExportDeclaration,
    HostAbiEffect,
    HostOpaqueDeclaration,
    HostRequireDeclaration,
    IdentifierNode,
    ImportAliasKind,
    ImportDeclaration,
    IncludeDeclaration,
    IfNode,
    ListLiteralNode,
    LiteralKind,
    LiteralNode,
    ModuleDeclaration,
    OperatorNode,
    PatternKind,
    PropagateNode,
    QuoteNode,
    QuoteEffect,
    ResultErrNode,
    ResultOkNode,
    TypedEmptyListNode,
    TypedEmptyMapNode,
    Visibility,
)
from nicole.errors import DiagnosticPhase, DiagnosticSeverity
from nicole.lexer import LexError, lex
from nicole.parser import ParseError, Parser
from nicole.tokens import TokenKind


def parse_source_raw(source: str):
    return Parser(lex(source)).parse()


def _wrap_in_module(source: str) -> str:
    lines = source.strip("\n").splitlines()
    indented = "\n".join(f"  {line}" if line else "" for line in lines)
    return f"module @test.phase1b\n{indented}\nend-module\n"


def parse_source(source: str):
    stripped = source.lstrip()
    if (
        stripped.startswith("module ")
        or stripped.startswith("import ")
        or stripped.startswith("include ")
    ):
        return parse_source_raw(source)
    return parse_source_raw(_wrap_in_module(source))


def _token_by_kind(tokens, kind: TokenKind, *, lexeme: str | None = None, index: int = 0):
    matches = [
        token
        for token in tokens
        if token.kind is kind and (lexeme is None or token.lexeme == lexeme)
    ]
    assert len(matches) > index
    return matches[index]


def test_parser_parses_module_declaration_with_export_declaration():
    program = parse_source_raw(
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    0\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )

    assert len(program.declarations) == 1
    module_decl = program.declarations[0]
    assert isinstance(module_decl, ModuleDeclaration)
    assert module_decl.name.parts == ("app",)
    assert isinstance(module_decl.items[0], type(program.words[0]))
    assert isinstance(module_decl.items[1], ExportDeclaration)
    assert module_decl.items[1].word_name == "run"


def test_parser_parses_import_declaration_forms():
    program = parse_source_raw(
        "module @app\n"
        "  import @math\n"
        "  import @math as m\n"
        "  import @math.utils\n"
        "  import @math.utils as u\n"
        "  : run { -- }\n"
        "  ;\n"
        "end-module\n"
    )

    assert len(program.declarations) == 1
    module_decl = program.declarations[0]
    assert isinstance(module_decl, ModuleDeclaration)
    assert isinstance(module_decl.items[0], ImportDeclaration)
    assert module_decl.items[0].target.parts == ("math",)
    assert module_decl.items[0].alias is None
    assert isinstance(module_decl.items[1], ImportDeclaration)
    assert module_decl.items[1].target.parts == ("math",)
    assert module_decl.items[1].alias == "m"
    assert isinstance(module_decl.items[2], ImportDeclaration)
    assert module_decl.items[2].target.parts == ("math", "utils")
    assert module_decl.items[2].alias is None
    assert isinstance(module_decl.items[3], ImportDeclaration)
    assert module_decl.items[3].target.parts == ("math", "utils")
    assert module_decl.items[3].alias == "u"


def test_parser_parses_grouped_import_with_prefix_alias():
    program = parse_source_raw(
        "module @app\n"
        "  import @host.io.{ open-file close-file FileHandle } as io\n"
        "end-module\n"
    )

    module_decl = program.declarations[0]
    assert isinstance(module_decl, ModuleDeclaration)
    grouped_import = module_decl.items[0]
    assert isinstance(grouped_import, ImportDeclaration)
    assert grouped_import.target.parts == ("host", "io")
    assert grouped_import.is_grouped is True
    assert grouped_import.grouped_members == ("open-file", "close-file", "FileHandle")
    assert grouped_import.alias == "io"
    assert grouped_import.alias_kind is ImportAliasKind.PREFIX


def test_parser_parses_grouped_import_with_as_star():
    program = parse_source_raw(
        "module @app\n"
        "  import @host.console.{ log read-line } as *\n"
        "end-module\n"
    )

    module_decl = program.declarations[0]
    assert isinstance(module_decl, ModuleDeclaration)
    grouped_import = module_decl.items[0]
    assert isinstance(grouped_import, ImportDeclaration)
    assert grouped_import.target.parts == ("host", "console")
    assert grouped_import.is_grouped is True
    assert grouped_import.grouped_members == ("log", "read-line")
    assert grouped_import.alias is None
    assert grouped_import.alias_kind is ImportAliasKind.STAR


def test_parser_parses_grouped_import_outside_host_namespace():
    program = parse_source_raw(
        "module @app\n"
        "  import @math.ops.{ add sub } as ops\n"
        "end-module\n"
    )

    module_decl = program.declarations[0]
    assert isinstance(module_decl, ModuleDeclaration)
    grouped_import = module_decl.items[0]
    assert isinstance(grouped_import, ImportDeclaration)
    assert grouped_import.target.parts == ("math", "ops")
    assert grouped_import.is_grouped is True
    assert grouped_import.grouped_members == ("add", "sub")
    assert grouped_import.alias == "ops"
    assert grouped_import.alias_kind is ImportAliasKind.PREFIX


def test_parser_rejects_grouped_import_with_empty_members():
    with pytest.raises(ParseError, match="grouped import must list at least one member"):
        parse_source_raw(
            "module @app\n"
            "  import @host.io.{ } as io\n"
            "end-module\n"
        )


def test_parser_rejects_grouped_import_without_alias():
    with pytest.raises(ParseError, match="grouped import requires an alias"):
        parse_source_raw(
            "module @app\n"
            "  import @host.io.{ open-file }\n"
            "end-module\n"
        )


def test_parser_grouped_import_without_alias_points_span_to_closing_brace():
    source = (
        "module @app\n"
        "  import @host.io.{ open-file }\n"
        "end-module\n"
    )
    tokens = lex(source)
    closing_brace = _token_by_kind(tokens, TokenKind.RBRACE, index=0)

    with pytest.raises(ParseError, match="grouped import requires an alias") as exc_info:
        parse_source_raw(source)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "PARSER_GROUPED_IMPORT_ALIAS_REQUIRED"
    assert diagnostic.span == closing_brace.span
    assert diagnostic.span.line == 2
    assert diagnostic.span.column == 31


def test_parser_rejects_grouped_import_with_invalid_alias():
    with pytest.raises(ParseError, match="expected grouped import alias"):
        parse_source_raw(
            "module @app\n"
            "  import @host.io.{ open-file } as {\n"
            "end-module\n"
        )


def test_parser_grouped_import_with_as_without_alias_points_span_to_as():
    source = (
        "module @app\n"
        "  import @host.io.{ open-file } as\n"
        "end-module\n"
    )
    tokens = lex(source)
    as_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="as", index=0)

    with pytest.raises(ParseError, match="expected grouped import alias") as exc_info:
        parse_source_raw(source)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "PARSER_GROUPED_IMPORT_ALIAS_INVALID"
    assert diagnostic.span == as_token.span
    assert diagnostic.span.line == 2
    assert diagnostic.span.column == 33


def test_parser_grouped_import_with_as_lbrace_points_span_to_lbrace():
    source = (
        "module @app\n"
        "  import @host.io.{ open-file } as {\n"
        "end-module\n"
    )
    tokens = lex(source)
    bad_token = _token_by_kind(tokens, TokenKind.LBRACE, index=1)

    with pytest.raises(ParseError, match="expected grouped import alias") as exc_info:
        parse_source_raw(source)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "PARSER_GROUPED_IMPORT_ALIAS_INVALID"
    assert diagnostic.span == bad_token.span
    assert diagnostic.span.line == 2
    assert diagnostic.span.column == 36


@pytest.mark.parametrize(
    "source",
    [
        "module @app\n  import @host.io.*\nend-module\n",
        "module @app\n  import @host.io.* as *\nend-module\n",
    ],
)
def test_parser_rejects_wildcard_like_import_forms(source):
    with pytest.raises(LexError, match="invalid module reference"):
        parse_source_raw(source)


def test_parser_parses_include_declaration():
    program = parse_source_raw('include "path.nic"\n')
    assert len(program.declarations) == 1
    include_decl = program.declarations[0]
    assert isinstance(include_decl, IncludeDeclaration)
    assert include_decl.path == "path.nic"


def test_parser_rejects_top_level_word_definition():
    with pytest.raises(ParseError, match="top-level word definition is not allowed"):
        parse_source_raw(": run { -- n:Int } 0 ;")


def test_parser_rejects_top_level_import():
    with pytest.raises(ParseError, match="imports are only allowed inside modules"):
        parse_source_raw("import @math\n")


def test_parser_rejects_import_after_module_definition():
    with pytest.raises(ParseError, match="imports must appear before module definitions"):
        parse_source_raw(
            "module @app\n"
            "  : run { -- }\n"
            "  ;\n"
            "  import @math\n"
            "end-module\n"
        )


def test_parser_rejects_export_outside_module():
    source = "export : run"
    tokens = lex(source)
    export_token = _token_by_kind(tokens, TokenKind.EXPORT)

    with pytest.raises(ParseError, match="export declaration is only allowed inside module") as exc_info:
        parse_source_raw(source)

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.phase is DiagnosticPhase.PARSER
    assert diagnostic.code == "PARSER_EXPORT_OUTSIDE_MODULE"
    assert diagnostic.message == "export declaration is only allowed inside module"
    assert diagnostic.span == export_token.span
    assert error.message == "export declaration is only allowed inside module"
    assert error.line == export_token.span.line
    assert error.column == export_token.span.column
    assert str(error) == f"{error.message} at {error.line}:{error.column}"


def test_parser_rejects_nested_module():
    with pytest.raises(ParseError, match="nested module declaration is not allowed"):
        parse_source_raw(
            "module @outer\n"
            "  module @inner\n"
            "  end-module\n"
            "end-module\n"
        )


def test_parser_rejects_import_inside_word_body():
    with pytest.raises(ParseError, match="unexpected token"):
        parse_source_raw(
            "module @app\n"
            "  : run { -- }\n"
            "    import @math\n"
            "  ;\n"
            "end-module\n"
        )


def test_parser_accepts_empty_host_module():
    program = parse_source_raw(
        "module @host\n"
        "end-module\n"
    )

    module_decl = program.declarations[0]
    assert isinstance(module_decl, ModuleDeclaration)
    assert module_decl.name.parts == ("host",)
    assert module_decl.is_host_module is True
    assert module_decl.items == ()


def test_parser_parses_host_require_with_dirty_effect():
    program = parse_source_raw(
        "module @host\n"
        "  require console.log { msg:String -- } dirty\n"
        "end-module\n"
    )

    module_decl = program.declarations[0]
    require_decl = module_decl.items[0]
    assert isinstance(require_decl, HostRequireDeclaration)
    assert require_decl.path.parts == ("console", "log")
    assert require_decl.signature.inputs[0].name == "msg"
    assert require_decl.signature.inputs[0].type_node.name == "String"
    assert require_decl.effect is HostAbiEffect.DIRTY


def test_parser_parses_host_require_with_pure_effect():
    program = parse_source_raw(
        "module @host\n"
        "  require clock.now-ms { -- n:Int } pure\n"
        "end-module\n"
    )

    module_decl = program.declarations[0]
    require_decl = module_decl.items[0]
    assert isinstance(require_decl, HostRequireDeclaration)
    assert require_decl.path.parts == ("clock", "now-ms")
    assert require_decl.signature.outputs[0].name == "n"
    assert require_decl.effect is HostAbiEffect.PURE


def test_parser_parses_host_require_with_canonical_host_output_type():
    program = parse_source_raw(
        "module @host\n"
        "  require file.open { path:String -- handle:@host.io.FileHandle } dirty\n"
        "end-module\n"
    )

    module_decl = program.declarations[0]
    require_decl = module_decl.items[0]
    assert isinstance(require_decl, HostRequireDeclaration)
    output = require_decl.signature.outputs[0]
    assert output.name == "handle"
    assert output.type_node.name == "@host.io.FileHandle"


def test_parser_rejects_host_require_with_anonymous_output_signature():
    with pytest.raises(ParseError, match="expected ':' in parameter"):
        parse_source_raw(
            "module @host\n"
            "  require clock.now-ms { -- Int } pure\n"
            "end-module\n"
        )


def test_parser_rejects_host_require_with_anonymous_input_signature():
    with pytest.raises(ParseError, match="expected ':' in parameter"):
        parse_source_raw(
            "module @host\n"
            "  require clock.accept { Int -- } dirty\n"
            "end-module\n"
        )


def test_parser_host_require_missing_effect_points_span_to_signature_end():
    source = (
        "module @host\n"
        "  require console.log { msg:String -- }\n"
        "end-module\n"
    )
    tokens = lex(source)
    signature_end = _token_by_kind(tokens, TokenKind.RBRACE, index=0)

    with pytest.raises(ParseError, match="host requirement must declare an effect") as exc_info:
        parse_source_raw(source)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "PARSER_HOST_REQUIRE_MISSING_EFFECT"
    assert diagnostic.span == signature_end.span
    assert diagnostic.span.line == 2
    assert diagnostic.span.column == 39


def test_parser_parses_host_opaque_declaration():
    program = parse_source_raw(
        "module @host\n"
        "  opaque io.FileHandle\n"
        "end-module\n"
    )

    module_decl = program.declarations[0]
    opaque_decl = module_decl.items[0]
    assert isinstance(opaque_decl, HostOpaqueDeclaration)
    assert opaque_decl.path.parts == ("io", "FileHandle")


def test_parser_parses_multiple_host_module_fragments():
    program = parse_source_raw(
        "module @host\n"
        "  require console.log { msg:String -- } dirty\n"
        "end-module\n"
        "module @host\n"
        "  opaque io.FileHandle\n"
        "end-module\n"
    )

    assert len(program.declarations) == 2
    first = program.declarations[0]
    second = program.declarations[1]
    assert isinstance(first, ModuleDeclaration)
    assert isinstance(second, ModuleDeclaration)
    assert first.is_host_module is True
    assert second.is_host_module is True
    assert isinstance(first.items[0], HostRequireDeclaration)
    assert isinstance(second.items[0], HostOpaqueDeclaration)


def test_parser_rejects_require_outside_host_module():
    with pytest.raises(ParseError, match="host ABI declarations are only allowed inside module @host"):
        parse_source_raw(
            "module @app\n"
            "  require console.log { msg:String -- } dirty\n"
            "end-module\n"
        )


def test_parser_rejects_opaque_outside_host_module():
    with pytest.raises(ParseError, match="host ABI declarations are only allowed inside module @host"):
        parse_source_raw(
            "module @app\n"
            "  opaque io.FileHandle\n"
            "end-module\n"
        )


def test_parser_rejects_top_level_require():
    with pytest.raises(ParseError, match="host ABI declarations are only allowed inside module @host"):
        parse_source_raw("require console.log { msg:String -- } dirty\n")


def test_parser_rejects_top_level_opaque():
    with pytest.raises(ParseError, match="host ABI declarations are only allowed inside module @host"):
        parse_source_raw("opaque io.FileHandle\n")


def test_parser_rejects_host_require_with_absolute_host_path():
    with pytest.raises(ParseError, match="host ABI paths are relative to @host"):
        parse_source_raw(
            "module @host\n"
            "  require @host.console.log { msg:String -- } dirty\n"
            "end-module\n"
        )


def test_parser_rejects_host_opaque_with_absolute_host_path():
    with pytest.raises(ParseError, match="host ABI paths are relative to @host"):
        parse_source_raw(
            "module @host\n"
            "  opaque @host.io.FileHandle\n"
            "end-module\n"
        )


@pytest.mark.parametrize(
    "source",
    [
        "module @host\n  import @math\nend-module\n",
        "module @host\n  include \"x.nic\"\nend-module\n",
        "module @host\n  export : run\nend-module\n",
        "module @host\n  : run { -- }\n  ;\nend-module\n",
        "module @host\n  console.log\nend-module\n",
    ],
)
def test_parser_rejects_non_host_abi_content_in_host_module(source):
    with pytest.raises(ParseError, match="module @host only allows require and opaque declarations"):
        parse_source_raw(source)


def test_parser_host_require_span_includes_effect_token():
    source = (
        "module @host\n"
        "  require console.log { msg:String -- } dirty\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    module_decl = program.declarations[0]
    require_decl = module_decl.items[0]
    require_token = _token_by_kind(tokens, TokenKind.REQUIRE)
    dirty_token = _token_by_kind(tokens, TokenKind.DIRTY)

    assert isinstance(require_decl, HostRequireDeclaration)
    assert require_decl.span.start == require_token.span.start
    assert require_decl.span.end == dirty_token.span.end


def test_parser_host_opaque_span_includes_path_token():
    source = (
        "module @host\n"
        "  opaque io.FileHandle\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    module_decl = program.declarations[0]
    opaque_decl = module_decl.items[0]
    opaque_token = _token_by_kind(tokens, TokenKind.OPAQUE)
    path_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="io.FileHandle")

    assert isinstance(opaque_decl, HostOpaqueDeclaration)
    assert opaque_decl.span.start == opaque_token.span.start
    assert opaque_decl.span.end == path_token.span.end


def test_parser_rejects_legacy_export_definition_form():
    with pytest.raises(ParseError):
        parse_source_raw(
            "module @app\n"
            "  : run { -- n:Int }\n"
            "    0\n"
            "  ;\n"
            "  export : run { -- n:Int }\n"
            "    0\n"
            "  ;\n"
            "end-module\n"
        )


def test_parser_rejects_export_dirty_form():
    with pytest.raises(ParseError):
        parse_source_raw(
            "module @app\n"
            "  : run { -- n:Int }\n"
            "    0\n"
            "  ;\n"
            "  export dirty : run\n"
            "end-module\n"
        )


def test_parser_rejects_dotted_user_word_definition():
    with pytest.raises(ParseError, match="cannot define qualified word name"):
        parse_source_raw(
            "module @app\n"
            "  : app.run { -- n:Int }\n"
            "    0\n"
            "  ;\n"
            "end-module\n"
        )


def test_parser_parses_word_signature_with_canonical_host_type():
    program = parse_source_raw(
        "module @app\n"
        "  : consume { handle:@host.io.FileHandle -- }\n"
        "  ;\n"
        "end-module\n"
    )
    word = program.words[0]
    assert word.signature.inputs[0].name == "handle"
    assert word.signature.inputs[0].type_node.name == "@host.io.FileHandle"


def test_parser_parses_generic_types_with_canonical_host_type_arguments():
    program = parse_source_raw(
        "module @app\n"
        "  : consume-list { xs:List<@host.io.FileHandle> -- }\n"
        "  ;\n"
        "  : consume-result { x:Result<@host.io.FileHandle,String> -- }\n"
        "  ;\n"
        "end-module\n"
    )
    consume_list = program.words[0]
    consume_result = program.words[1]
    list_arg = consume_list.signature.inputs[0].type_node.args[0]
    result_first_arg = consume_result.signature.inputs[0].type_node.args[0]

    assert list_arg.name == "@host.io.FileHandle"
    assert result_first_arg.name == "@host.io.FileHandle"


def test_parser_keeps_legacy_host_dotted_type_name():
    program = parse_source_raw(
        "module @app\n"
        "  : consume { handle:host.io.FileHandle -- }\n"
        "  ;\n"
        "end-module\n"
    )
    word = program.words[0]
    assert word.signature.inputs[0].type_node.name == "host.io.FileHandle"


def test_parser_rejects_non_host_qualified_module_type():
    with pytest.raises(ParseError, match="malformed type"):
        parse_source_raw(
            "module @app\n"
            "  : consume { value:@app.Type -- }\n"
            "  ;\n"
            "end-module\n"
        )


def test_parser_accepts_qualified_reference_atom():
    program = parse_source_raw(
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    @math.sqrt drop\n"
        "    @app.run drop\n"
        "    @a.b.c drop\n"
        "    0\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )
    run_word = program.words[0]
    assert isinstance(run_word.body.items[0], IdentifierNode)
    assert run_word.body.items[0].name == "@math.sqrt"
    assert isinstance(run_word.body.items[2], IdentifierNode)
    assert run_word.body.items[2].name == "@app.run"
    assert isinstance(run_word.body.items[4], IdentifierNode)
    assert run_word.body.items[4].name == "@a.b.c"


def test_parser_rejects_bare_module_reference_atom():
    with pytest.raises(
        ParseError,
        match="qualified module reference in expression requires a word segment",
    ):
        parse_source_raw(
            "module @app\n"
            "  : run { -- n:Int }\n"
            "    @math drop\n"
            "    0\n"
            "  ;\n"
            "  export : run\n"
            "end-module\n"
        )


def test_parser_simple_word():
    program = parse_source(": add { a:Int b:Int -- r:Int } a b + ;")
    word = program.words[0]

    assert word.name == "add"
    assert len(word.signature.inputs) == 2
    assert len(word.signature.outputs) == 1
    assert isinstance(word.body.items[0], IdentifierNode)
    assert isinstance(word.body.items[1], IdentifierNode)
    assert isinstance(word.body.items[2], OperatorNode)


def test_parser_accepts_float_operators():
    program = parse_source(": addf { x:Float y:Float -- z:Float } x y +. ;")
    operator = program.words[0].body.items[2]

    assert isinstance(operator, OperatorNode)
    assert operator.operator == "+."


def test_parser_rejects_bare_slash_operator():
    with pytest.raises(Exception):
        parse_source(": bad { x:Int y:Int -- z:Int } x y / ;")


def test_parser_rejects_duplicate_word_input_names():
    with pytest.raises(ParseError, match="duplicate local name in word frame"):
        parse_source(
            ": bad { x:Int x:Int -- y:Int }\n"
            "  x\n"
            ";"
        )


def test_parser_duplicate_word_input_name_exposes_structured_diagnostic() -> None:
    source = (
        "module @app\n"
        "  : bad { x:Int x:Int -- y:Int }\n"
        "    x\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    duplicate_param_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="x", index=1)
    duplicate_param_type_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="Int", index=1)

    with pytest.raises(ParseError, match="duplicate local name in word frame") as exc_info:
        parse_source_raw(source)

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.phase is DiagnosticPhase.PARSER
    assert diagnostic.code == "PARSER_DUPLICATE_LOCAL_NAME"
    assert diagnostic.message == "duplicate local name in word frame"
    assert diagnostic.span is not None
    assert diagnostic.span.start == duplicate_param_token.span.start
    assert diagnostic.span.end == duplicate_param_type_token.span.end
    assert error.message == "duplicate local name in word frame"
    assert error.line == duplicate_param_token.span.line
    assert error.column == duplicate_param_token.span.column
    assert str(error) == f"{error.message} at {error.line}:{error.column}"


def test_parser_if_has_no_condition_field():
    program = parse_source(
        ": abs { x:Int -- y:Int }\n"
        "  x 0 < if\n"
        "    0 x -\n"
        "  else\n"
        "    x\n"
        "  end\n"
        ";"
    )
    if_node = program.words[0].body.items[3]

    assert isinstance(if_node, IfNode)
    assert not hasattr(if_node, "condition")
    assert len(if_node.then_block.items) == 3
    assert len(if_node.else_block.items) == 1


def test_parser_case_has_no_scrutinee_field():
    program = parse_source(
        ": sign-label { n:Int -- text:String }\n"
        "  n case\n"
        "    0 => \"zero\"\n"
        "    1 => \"one\"\n"
        "    _ => \"many\"\n"
        "  end\n"
        ";"
    )
    case_node = program.words[0].body.items[1]

    assert isinstance(case_node, CaseNode)
    assert not hasattr(case_node, "scrutinee")
    assert [branch.pattern.kind for branch in case_node.branches] == [
        PatternKind.LITERAL,
        PatternKind.LITERAL,
        PatternKind.WILDCARD,
    ]
    assert all(branch.guard is None for branch in case_node.branches)


def test_parser_case_accepts_negative_int_literal_pattern():
    program = parse_source(
        ": sign-label { n:Int -- text:String }\n"
        "  n case\n"
        "    -1 => \"minus one\"\n"
        "    _ => \"other\"\n"
        "  end\n"
        ";"
    )
    case_node = program.words[0].body.items[1]

    assert isinstance(case_node, CaseNode)
    assert case_node.branches[0].pattern.kind is PatternKind.LITERAL
    assert case_node.branches[0].pattern.value == -1


def test_parser_case_with_guarded_branch_parses():
    program = parse_source(
        ": classify { r:Result<Int,MapError> -- text:String }\n"
        "  r case\n"
        "    Ok(v) when v 0 > => \"positive\"\n"
        "    _ => \"other\"\n"
        "  end\n"
        ";"
    )
    case_node = program.words[0].body.items[1]
    assert isinstance(case_node, CaseNode)

    guarded = case_node.branches[0]
    assert guarded.pattern.kind is PatternKind.OK
    assert guarded.pattern.binding == "v"
    assert guarded.guard is not None
    assert isinstance(guarded.guard.items[0], IdentifierNode)
    assert isinstance(guarded.guard.items[1], LiteralNode)
    assert isinstance(guarded.guard.items[2], OperatorNode)


def test_parser_case_with_mixed_guarded_and_unguarded_branches_parses():
    program = parse_source(
        ": classify { n:Int -- text:String }\n"
        "  n case\n"
        "    0 when true => \"zero\"\n"
        "    1 => \"one\"\n"
        "    _ when false => \"never\"\n"
        "    _ => \"many\"\n"
        "  end\n"
        ";"
    )
    case_node = program.words[0].body.items[1]
    assert isinstance(case_node, CaseNode)
    assert case_node.branches[0].guard is not None
    assert case_node.branches[1].guard is None
    assert case_node.branches[2].guard is not None
    assert case_node.branches[3].guard is None


def test_parser_case_node_span_includes_terminating_end():
    source = (
        "module @app\n"
        "  : classify { n:Int -- text:String }\n"
        "    n case\n"
        "      0 => \"zero\"\n"
        "      _ => \"many\"\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    case_node = program.words[0].body.items[1]
    case_token = _token_by_kind(tokens, TokenKind.CASE, index=0)
    end_token = _token_by_kind(tokens, TokenKind.END, index=0)

    assert isinstance(case_node, CaseNode)
    assert case_node.span.start == case_token.span.start
    assert case_node.span.end == end_token.span.end


def test_parser_ok_constructor_pattern_span_includes_closing_rparen():
    source = (
        "module @app\n"
        "  : classify { r:Result<Int,MapError> -- n:Int }\n"
        "    r case\n"
        "      Ok(v) => v\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    pattern = program.words[0].body.items[1].branches[0].pattern
    ok_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="Ok", index=0)
    rparen_token = _token_by_kind(tokens, TokenKind.RPAREN, index=0)

    assert pattern.kind is PatternKind.OK
    assert pattern.span.start == ok_token.span.start
    assert pattern.span.end == rparen_token.span.end


def test_parser_err_constructor_pattern_span_includes_closing_rparen():
    source = (
        "module @app\n"
        "  : classify { r:Result<Int,MapError> -- n:Int }\n"
        "    r case\n"
        "      Err(e) => 0\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    pattern = program.words[0].body.items[1].branches[0].pattern
    err_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="Err", index=0)
    rparen_token = _token_by_kind(tokens, TokenKind.RPAREN, index=0)

    assert pattern.kind is PatternKind.ERR
    assert pattern.span.start == err_token.span.start
    assert pattern.span.end == rparen_token.span.end


def test_parser_case_branch_first_ends_at_next_branch_pattern_boundary():
    source = (
        "module @app\n"
        "  : classify { n:Int -- text:String }\n"
        "    n case\n"
        "      0 => \"zero\"\n"
        "      1 => \"one\"\n"
        "      _ => \"many\"\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    case_node = program.words[0].body.items[1]
    first_branch = case_node.branches[0]
    second_branch = case_node.branches[1]
    first_pattern_token = _token_by_kind(tokens, TokenKind.INT_LITERAL, lexeme="0", index=0)
    second_pattern_token = _token_by_kind(tokens, TokenKind.INT_LITERAL, lexeme="1", index=0)

    assert isinstance(case_node, CaseNode)
    assert first_branch.span.start == first_pattern_token.span.start
    assert first_branch.span.end == second_pattern_token.span.start
    assert second_branch.span.start == second_pattern_token.span.start


def test_parser_case_branch_final_ends_at_enclosing_end_boundary():
    source = (
        "module @app\n"
        "  : classify { n:Int -- text:String }\n"
        "    n case\n"
        "      0 => \"zero\"\n"
        "      _ => \"many\"\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    case_node = program.words[0].body.items[1]
    final_branch = case_node.branches[-1]
    wildcard_token = _token_by_kind(tokens, TokenKind.UNDERSCORE, index=0)
    end_token = _token_by_kind(tokens, TokenKind.END, index=0)

    assert isinstance(case_node, CaseNode)
    assert final_branch.span.start == wildcard_token.span.start
    assert final_branch.span.end == end_token.span.start


def test_parser_case_branch_with_body_items_still_uses_boundary_rule():
    source = (
        "module @app\n"
        "  : classify { n:Int -- text:String }\n"
        "    n case\n"
        "      0 => \"zero\" drop\n"
        "      _ => \"many\"\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    case_node = program.words[0].body.items[1]
    first_branch = case_node.branches[0]
    second_pattern_token = _token_by_kind(tokens, TokenKind.UNDERSCORE, index=0)

    assert isinstance(case_node, CaseNode)
    assert len(first_branch.body.items) == 2
    assert first_branch.span.end == second_pattern_token.span.start


def test_parser_nested_case_preserves_outer_ranges():
    source = (
        "module @app\n"
        "  : nested { x:Int y:Int -- n:Int }\n"
        "    x case\n"
        "      0 => y case\n"
        "        1 => 1\n"
        "        _ => 2\n"
        "      end\n"
        "      _ => 3\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    outer_case = program.words[0].body.items[1]
    inner_case = outer_case.branches[0].body.items[1]
    outer_case_token = _token_by_kind(tokens, TokenKind.CASE, index=0)
    inner_case_token = _token_by_kind(tokens, TokenKind.CASE, index=1)
    inner_end_token = _token_by_kind(tokens, TokenKind.END, index=0)
    outer_end_token = _token_by_kind(tokens, TokenKind.END, index=1)

    assert isinstance(outer_case, CaseNode)
    assert isinstance(inner_case, CaseNode)
    assert inner_case.span.start == inner_case_token.span.start
    assert inner_case.span.end == inner_end_token.span.end
    assert outer_case.span.start == outer_case_token.span.start
    assert outer_case.span.end == outer_end_token.span.end


def test_parser_quotation():
    program = parse_source(": q { -- } :[ | x:Int -- y:Int | x 1 + ;] ;")
    quote = program.words[0].body.items[0]

    assert isinstance(quote, QuoteNode)
    assert len(quote.captures) == 0
    assert len(quote.inputs) == 1
    assert len(quote.outputs) == 1
    assert isinstance(quote.body.items[0], IdentifierNode)
    assert isinstance(quote.body.items[1], LiteralNode)
    assert isinstance(quote.body.items[2], OperatorNode)


def test_parser_quotation_with_capture_and_quote_end():
    program = parse_source(": q { -- } :[ a:Int | x:Int -- y:Int | x a + ;] ;")
    quote = program.words[0].body.items[0]

    assert isinstance(quote, QuoteNode)
    assert len(quote.captures) == 1
    assert quote.captures[0].name == "a"
    assert len(quote.inputs) == 1
    assert len(quote.outputs) == 1


def test_parser_rejects_duplicate_quotation_input_names():
    with pytest.raises(ParseError, match="duplicate local name in quotation frame"):
        parse_source(": q { -- } :[ | x:Int x:Int -- y:Int | x ;] ;")


def test_parser_rejects_duplicate_quotation_capture_names():
    with pytest.raises(ParseError, match="duplicate local name in quotation frame"):
        parse_source(": q { -- } :[ a:Int a:Int | x:Int -- y:Int | x ;] ;")


def test_parser_rejects_duplicate_quotation_capture_and_input_names():
    with pytest.raises(ParseError, match="duplicate local name in quotation frame"):
        parse_source(": q { -- } :[ x:Int | x:Int -- y:Int | x ;] ;")


def test_parser_rejects_quote_closed_with_rbracket_only():
    with pytest.raises(ParseError):
        parse_source(": q { -- } :[ | x:Int -- y:Int | x 1 + ] ;")


def test_parser_list_literal():
    program = parse_source(": listy { -- xs:List<Int> } [1, 2, 3] ;")
    list_node = program.words[0].body.items[0]

    assert isinstance(list_node, ListLiteralNode)
    assert [element.value for element in list_node.elements] == [1, 2, 3]


def test_parser_negative_int_literal_is_single_literal_node():
    program = parse_source(": neg { -- n:Int } -5 ;")
    literal = program.words[0].body.items[0]

    assert isinstance(literal, LiteralNode)
    assert literal.kind is LiteralKind.INT
    assert literal.value == -5
    assert literal.raw == "-5"


def test_parser_negative_float_literal_is_single_literal_node():
    program = parse_source(": negf { -- n:Float } -3.5 ;")
    literal = program.words[0].body.items[0]

    assert isinstance(literal, LiteralNode)
    assert literal.kind is LiteralKind.FLOAT
    assert literal.value == -3.5
    assert literal.raw == "-3.5"


def test_parser_negative_list_literal():
    program = parse_source(": listy { -- xs:List<Int> } [-1, -2, 3] ;")
    list_node = program.words[0].body.items[0]

    assert isinstance(list_node, ListLiteralNode)
    assert [element.value for element in list_node.elements] == [-1, -2, 3]


def test_parser_accepts_typed_empty_list():
    program = parse_source(": empty { -- xs:List<Int> } []:List<Int> ;")
    list_node = program.words[0].body.items[0]

    assert isinstance(list_node, TypedEmptyListNode)
    assert list_node.type_node.name == "List"
    assert list_node.type_node.args[0].name == "Int"


def test_parser_accepts_typed_empty_nested_list():
    program = parse_source(
        ": empty-nested { -- xs:List<Map<String,Int>> } []:List<Map<String,Int>> ;"
    )
    list_node = program.words[0].body.items[0]

    assert isinstance(list_node, TypedEmptyListNode)
    assert list_node.type_node.name == "List"
    inner_type = list_node.type_node.args[0]
    assert inner_type.name == "Map"
    assert inner_type.args[0].name == "String"
    assert inner_type.args[1].name == "Int"


def test_parser_rejects_bare_empty_list():
    with pytest.raises(ParseError):
        parse_source(": bad { -- xs:List<Int> } [] ;")


def test_parser_invalid_empty_list_annotation_uses_type_span() -> None:
    source = (
        "module @app\n"
        "  : bad { -- xs:List<Int> }\n"
        "    []:Map<String,Int>\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    type_name_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="Map", index=0)
    type_end_token = _token_by_kind(tokens, TokenKind.GT, index=1)

    with pytest.raises(ParseError, match="empty list requires List<T> annotation") as exc_info:
        parse_source_raw(source)

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.code == "PARSER_INVALID_EMPTY_LIST_ANNOTATION"
    assert diagnostic.span is not None
    assert diagnostic.span.start == type_name_token.span.start
    assert diagnostic.span.end == type_end_token.span.end
    assert error.line == type_name_token.span.line
    assert error.column == type_name_token.span.column


def test_parser_accepts_typed_empty_map():
    program = parse_source(": empty { -- m:Map<String,Int> } map.empty:Map<String,Int> ;")
    map_node = program.words[0].body.items[0]

    assert isinstance(map_node, TypedEmptyMapNode)
    assert map_node.type_node.name == "Map"
    assert map_node.type_node.args[0].name == "String"
    assert map_node.type_node.args[1].name == "Int"


def test_parser_accepts_typed_empty_map_with_nested_quote_type():
    program = parse_source(
        ": empty-nested { -- m:Map<String,Quote<{ | x:Int -- y:Int }>> } "
        "map.empty:Map<String,Quote<{ | x:Int -- y:Int }>> ;"
    )
    map_node = program.words[0].body.items[0]

    assert isinstance(map_node, TypedEmptyMapNode)
    assert map_node.type_node.name == "Map"
    assert map_node.type_node.args[0].name == "String"
    quote_type = map_node.type_node.args[1]
    assert quote_type.name == "Quote"
    assert len(quote_type.args) == 1
    assert quote_type.args[0].effect_kind is QuoteEffect.PURE


def test_parser_parses_dirtyquote_type_as_dirty_effect_kind():
    program = parse_source(
        ": make { -- q:DirtyQuote<{ | x:Int -- y:Int }> }\n"
        "  :[ | x:Int -- y:Int | x ;]\n"
        ";"
    )
    quote_type = program.words[0].signature.outputs[0].type_node

    assert quote_type.name == "Quote"
    assert len(quote_type.args) == 1
    assert quote_type.args[0].effect_kind is QuoteEffect.DIRTY


def test_parser_accepts_dirtyquote_nested_in_generic_type():
    program = parse_source(
        ": typed { -- m:Map<String,DirtyQuote<{ | x:Int -- y:Int }>> }\n"
        "  map.empty:Map<String,DirtyQuote<{ | x:Int -- y:Int }>>\n"
        ";"
    )
    inner_type = program.words[0].signature.outputs[0].type_node.args[1]

    assert inner_type.name == "Quote"
    assert inner_type.args[0].effect_kind is QuoteEffect.DIRTY


def test_parser_rejects_bare_empty_map():
    with pytest.raises(ParseError):
        parse_source(": bad { -- m:Map<String,Int> } map.empty ;")


def test_parser_invalid_empty_map_annotation_uses_type_span() -> None:
    source = (
        "module @app\n"
        "  : bad { -- xs:Map<String,Int> }\n"
        "    map.empty:List<Int>\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    type_name_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="List", index=0)
    type_end_token = _token_by_kind(tokens, TokenKind.GT, index=1)

    with pytest.raises(ParseError, match="map.empty requires Map<K,V> annotation") as exc_info:
        parse_source_raw(source)

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.code == "PARSER_INVALID_EMPTY_MAP_ANNOTATION"
    assert diagnostic.span is not None
    assert diagnostic.span.start == type_name_token.span.start
    assert diagnostic.span.end == type_end_token.span.end
    assert error.line == type_name_token.span.line
    assert error.column == type_name_token.span.column


def test_parser_pub_and_export():
    program = parse_source_raw(
        "module @app\n"
        "  pub : foo { -- }\n"
        "    1\n"
        "  ;\n"
        "  export : foo\n"
        "end-module\n"
    )
    module_decl = program.declarations[0]
    assert isinstance(module_decl, ModuleDeclaration)
    assert program.words[0].visibility is Visibility.PUB
    assert isinstance(module_decl.items[1], ExportDeclaration)
    assert module_decl.items[1].word_name == "foo"


def test_parser_accepts_dirty_word_definition():
    program = parse_source("dirty : foo { -- } ;")

    assert program.words[0].name == "foo"
    assert program.words[0].visibility is Visibility.PRIVATE
    assert program.words[0].is_dirty_annotation is True


def test_parser_accepts_pub_dirty_word_definition():
    program = parse_source("pub dirty : foo { -- } ;")

    assert program.words[0].name == "foo"
    assert program.words[0].visibility is Visibility.PUB
    assert program.words[0].is_dirty_annotation is True


@pytest.mark.parametrize(
    "source",
    [
        "dirty pub : foo { -- } ;",
        ": dirty foo { -- } ;",
    ],
)
def test_parser_rejects_invalid_dirty_modifier_ordering(source):
    with pytest.raises(ParseError):
        parse_source(source)


def test_parser_rejects_export_inside_subword():
    with pytest.raises(ParseError):
        parse_source(
            ": outer { -- }\n"
            "  export : inner\n"
            ";"
        )


def test_parser_nested_subword():
    program = parse_source(
        ": invoice { price:Int qty:Int -- total:Int }\n"
        "  : subtotal { price:Int qty:Int -- amount:Int }\n"
        "    price qty *\n"
        "  ;\n"
        "  price qty subtotal\n"
        ";"
    )

    parent = program.words[0]
    assert len(parent.nested_words) == 1
    assert parent.nested_words[0].name == "subtotal"


def test_parser_accepts_subword_reusing_parent_local_name():
    program = parse_source(
        ": foo { x:Int -- y:Int }\n"
        "  : bar { x:Int -- y:Int }\n"
        "    1 x +\n"
        "  ;\n"
        "  3 bar\n"
        "  x\n"
        "  +\n"
        ";"
    )

    assert program.words[0].name == "foo"
    assert program.words[0].nested_words[0].signature.inputs[0].name == "x"


def test_parser_malformed_input_raises_parse_error():
    with pytest.raises(ParseError):
        parse_source(": bad { -- } 1")


def test_parser_malformed_type_exposes_structured_diagnostic() -> None:
    source = (
        "module @app\n"
        "  : broken { -- xs:List<Int }\n"
        "    0\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    closing_rbrace = _token_by_kind(tokens, TokenKind.RBRACE, index=0)

    with pytest.raises(ParseError, match="malformed type") as exc_info:
        parse_source_raw(source)

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.phase is DiagnosticPhase.PARSER
    assert diagnostic.code == "PARSER_INVALID_TYPE"
    assert diagnostic.message == "malformed type"
    assert diagnostic.span == closing_rbrace.span
    assert error.message == "malformed type"
    assert error.line == closing_rbrace.span.line
    assert error.column == closing_rbrace.span.column
    assert str(error) == f"{error.message} at {error.line}:{error.column}"


def test_parser_rejects_arbitrary_identifier_pattern():
    with pytest.raises(ParseError):
        parse_source(
            ": bad-case { n:Int -- text:String }\n"
            "  n case\n"
            "    foo => \"bad\"\n"
            "  end\n"
            ";"
        )


def test_parser_rejects_float_literal_pattern():
    with pytest.raises(ParseError):
        parse_source(
            ": bad-case { n:Float -- text:String }\n"
            "  n case\n"
            "    1.5 => \"bad\"\n"
            "    _ => \"ok\"\n"
            "  end\n"
            ";"
        )


def test_parser_rejects_negative_float_literal_pattern():
    with pytest.raises(ParseError):
        parse_source(
            ": bad-case { n:Float -- text:String }\n"
            "  n case\n"
            "    -3.5 => \"bad\"\n"
            "    _ => \"ok\"\n"
            "  end\n"
            ";"
        )


def test_parser_accepts_ok_binding_pattern():
    program = parse_source(
        ": ok-case { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        "    Ok(v) => v\n"
        "  end\n"
        ";"
    )
    branch = program.words[0].body.items[1].branches[0]
    assert branch.pattern.kind is PatternKind.OK
    assert branch.pattern.binding == "v"
    assert branch.pattern.value is None


def test_parser_accepts_err_binding_pattern():
    program = parse_source(
        ": err-case { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        "    Err(e) => 0\n"
        "  end\n"
        ";"
    )
    branch = program.words[0].body.items[1].branches[0]
    assert branch.pattern.kind is PatternKind.ERR
    assert branch.pattern.binding == "e"
    assert branch.pattern.value is None


@pytest.mark.parametrize("variant_name", ["OutOfBounds", "MissingKey"])
def test_parser_accepts_err_variant_pattern(variant_name):
    program = parse_source(
        ": err-case { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        f"    Err({variant_name}) => 0\n"
        "  end\n"
        ";"
    )
    branch = program.words[0].body.items[1].branches[0]
    assert branch.pattern.kind is PatternKind.ERR
    assert branch.pattern.value == variant_name
    assert branch.pattern.binding is None


@pytest.mark.parametrize(
    "source",
    [
        (
            ": bad-case { n:Int -- text:String }\n"
            "  n case\n"
            "    foo => \"bad\"\n"
            "  end\n"
            ";"
        ),
        (
            ": bad-case { n:Int -- text:String }\n"
            "  n case\n"
            "    Some(v) => \"bad\"\n"
            "  end\n"
            ";"
        ),
    ],
)
def test_parser_rejects_invalid_constructor_patterns(source):
    with pytest.raises(ParseError):
        parse_source(source)


@pytest.mark.parametrize(
    "source",
    [
        (
            ": bad-case { r:Result<Int,MapError> -- text:String }\n"
            "  r case\n"
            "    Ok(Err(e)) => \"bad\"\n"
            "  end\n"
            ";"
        ),
        (
            ": bad-case { r:Result<Int,MapError> -- text:String }\n"
            "  r case\n"
            "    Ok(a,b) => \"bad\"\n"
            "  end\n"
            ";"
        ),
        (
            ": bad-case { r:Result<Int,MapError> -- text:String }\n"
            "  r case\n"
            "    Some(v) => \"bad\"\n"
            "  end\n"
            ";"
        ),
    ],
)
def test_parser_constructor_pattern_capabilities_remain_unchanged(source):
    with pytest.raises(ParseError):
        parse_source(source)


@pytest.mark.parametrize(
    "source",
    [
        (
            ": bad-case { n:Int -- text:String }\n"
            "  n case\n"
            "    0 if true => \"bad\"\n"
            "    _ => \"ok\"\n"
            "  end\n"
            ";"
        ),
        (
            ": bad-case { n:Int -- text:String }\n"
            "  n case\n"
            "    0 => when true \"bad\"\n"
            "    _ => \"ok\"\n"
            "  end\n"
            ";"
        ),
    ],
)
def test_parser_rejects_invalid_guard_syntax(source):
    with pytest.raises(ParseError):
        parse_source(source)


def test_parser_accepts_ok_result_constructor():
    program = parse_source(
        ": ok-result { -- r:Result<Int,MapError> }\n"
        "  1 Ok!\n"
        ";"
    )
    assert isinstance(program.words[0].body.items[1], ResultOkNode)


def test_parser_accepts_err_result_constructor():
    program = parse_source(
        ": err-result { -- r:Result<Int,MapError> }\n"
        "  MissingKey Err!\n"
        ";"
    )
    assert isinstance(program.words[0].body.items[1], ResultErrNode)


def test_parser_accepts_propagation_operator():
    program = parse_source(
        ": use-propagation { cfg:Map<String,Int> -- r:Result<Int,MapError> }\n"
        "  cfg \"timeout\" map.get ?\n"
        "  Ok!\n"
        ";"
    )
    assert isinstance(program.words[0].body.items[3], PropagateNode)
    assert isinstance(program.words[0].body.items[4], ResultOkNode)


@pytest.mark.parametrize(
    "source",
    [
        ": bad { -- r:Result<Int,MapError> } Ok(1) ;",
        ": bad { -- r:Result<String,MapError> } Err(MissingKey) ;",
    ],
)
def test_parser_rejects_result_constructor_call_syntax(source):
    with pytest.raises(ParseError):
        parse_source(source)


def test_parser_nested_constructor_pattern_error_uses_nested_token_span() -> None:
    source = (
        "module @app\n"
        "  : bad-case { r:Result<Int,MapError> -- text:String }\n"
        "    r case\n"
        "      Ok(Err(e)) => \"bad\"\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    nested_constructor_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="Err", index=0)

    with pytest.raises(ParseError, match="unexpected token") as exc_info:
        parse_source_raw(source)

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.code == "PARSER_INVALID_PATTERN"
    assert diagnostic.span == nested_constructor_token.span
    assert error.line == nested_constructor_token.span.line
    assert error.column == nested_constructor_token.span.column


def test_parser_constructor_pattern_comma_error_uses_comma_span() -> None:
    source = (
        "module @app\n"
        "  : bad-case { r:Result<Int,MapError> -- text:String }\n"
        "    r case\n"
        "      Ok(a,b) => \"bad\"\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    comma_token = next(token for token in tokens if token.kind is TokenKind.COMMA and token.span.line == 4)

    with pytest.raises(ParseError, match="unexpected token") as exc_info:
        parse_source_raw(source)

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.code == "PARSER_INVALID_PATTERN"
    assert diagnostic.span == comma_token.span
    assert error.line == comma_token.span.line
    assert error.column == comma_token.span.column


@pytest.mark.parametrize(
    "source",
    [
        ": host.log { -- } ;",
        "pub : host.log { -- } ;",
    ],
)
def test_parser_rejects_host_word_definitions(source):
    with pytest.raises(ParseError, match=r"cannot define reserved namespace word"):
        parse_source(source)


def test_parser_rejects_export_declaration_with_qualified_name():
    with pytest.raises(ParseError, match="export declaration expects local word name"):
        parse_source_raw(
            "module @app\n"
            "  : run { -- }\n"
            "  ;\n"
            "  export : host.log\n"
            "end-module\n"
        )


def test_parser_export_qualified_name_error_uses_exported_token_span() -> None:
    source = (
        "module @app\n"
        "  : run { -- }\n"
        "  ;\n"
        "  export : host.log\n"
        "end-module\n"
    )
    tokens = lex(source)
    exported_word_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="host.log")
    end_module_token = _token_by_kind(tokens, TokenKind.END_MODULE, index=0)

    with pytest.raises(ParseError, match="export declaration expects local word name") as exc_info:
        parse_source_raw(source)

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.code == "PARSER_EXPORT_EXPECTS_LOCAL_WORD"
    assert diagnostic.span == exported_word_token.span
    assert diagnostic.span != end_module_token.span
    assert error.line == exported_word_token.span.line
    assert error.column == exported_word_token.span.column


@pytest.mark.parametrize(
    "name",
    [
        "call",
        "MissingKey",
        "OutOfBounds",
        "result.custom",
        "list.custom",
        "map.custom",
    ],
)
def test_parser_rejects_reserved_top_level_word_names(name):
    with pytest.raises(ParseError):
        parse_source(f": {name} {{ -- }} ;")


def test_parser_rejects_reserved_top_level_word_name_dirty():
    with pytest.raises(ParseError, match=r"dirty.*reserved|reserved.*dirty"):
        parse_source(": dirty { -- } ;")


@pytest.mark.parametrize(
    "name",
    [
        "call",
        "MissingKey",
        "OutOfBounds",
        "result.custom",
        "list.custom",
        "map.custom",
    ],
)
def test_parser_rejects_reserved_subword_names(name):
    with pytest.raises(ParseError):
        parse_source(
            ": outer { -- }\n"
            f"  : {name} {{ -- }} ;\n"
            ";"
        )


def test_parser_rejects_reserved_subword_name_dirty():
    with pytest.raises(ParseError, match=r"dirty.*reserved|reserved.*dirty"):
        parse_source(
            ": outer { -- }\n"
            "  : dirty { -- } ;\n"
            ";"
        )


def test_parser_rejects_reserved_local_name_dirty_in_signature_input():
    with pytest.raises(ParseError, match=r"dirty.*reserved|reserved.*dirty"):
        parse_source(": foo { dirty:Int -- x:Int } dirty ;")


def test_parser_rejects_reserved_capture_name_dirty():
    with pytest.raises(ParseError, match=r"dirty.*reserved|reserved.*dirty"):
        parse_source(": foo { -- } :[ dirty:Int | x:Int -- y:Int | x ;] ;")


def test_parser_rejects_reserved_output_label_dirty():
    with pytest.raises(ParseError, match=r"dirty.*reserved|reserved.*dirty"):
        parse_source(": foo { -- dirty:Int } 1 ;")


def test_parser_accepts_dirty_prefixed_non_reserved_names():
    program = parse_source(": dirty-int { mydirtyvalue:Int -- out:Int } mydirtyvalue ;")

    assert program.words[0].name == "dirty-int"
    assert program.words[0].signature.inputs[0].name == "mydirtyvalue"


def test_parser_accepts_additional_non_exact_dirty_identifiers():
    program = parse_source(
        ": dirty_log { -- } ;\n"
        ": is-dirty { -- } ;"
    )

    assert program.words[0].name == "dirty_log"
    assert program.words[1].name == "is-dirty"


def test_parser_rejects_definition_name_with_dot():
    with pytest.raises(ParseError, match="cannot define qualified word name"):
        parse_source(": dirty.value { -- } ;")


def test_parser_accepts_host_word_usage():
    program = parse_source(": log { msg:String -- } msg host.log ;")
    assert isinstance(program.words[0].body.items[0], IdentifierNode)
    assert isinstance(program.words[0].body.items[1], IdentifierNode)
    assert program.words[0].body.items[1].name == "host.log"


@pytest.mark.parametrize(
    "source",
    [
        (
            ": main { flag:Bool -- n:Int }\n"
            "  flag if\n"
            "    : helper { -- n:Int }\n"
            "      1\n"
            "    ;\n"
            "    helper\n"
            "  else\n"
            "    0\n"
            "  end\n"
            ";"
        ),
        (
            ": main { n:Int -- text:String }\n"
            "  n case\n"
            "    0 =>\n"
            "      : helper { -- n:Int }\n"
            "        1\n"
            "      ;\n"
            "      helper\n"
            "  end\n"
            ";"
        ),
        (
            ": main { -- q:Quote<{ | -- }> }\n"
            "  :[ | -- | : helper { -- n:Int }\n"
            "      1\n"
            "    ; ;]\n"
            ";"
        ),
    ],
)
def test_parser_rejects_nested_word_defs_inside_control_flow(source):
    with pytest.raises(ParseError):
        parse_source(source)


def test_parser_program_span_non_empty_ends_at_eof():
    source = 'include "path.nic"\n'
    tokens = lex(source)
    program = parse_source_raw(source)
    eof = _token_by_kind(tokens, TokenKind.EOF)

    assert len(program.declarations) == 1
    assert program.span.start == program.declarations[0].span.start
    assert program.span.end == eof.span.end


def test_parser_program_span_empty_uses_eof_zero_length_span():
    source = ""
    tokens = lex(source)
    program = parse_source_raw(source)
    eof = _token_by_kind(tokens, TokenKind.EOF)

    assert program.declarations == ()
    assert program.words == ()
    assert program.span.start == eof.span.start
    assert program.span.end == eof.span.end
    assert program.span.start == program.span.end


def test_parser_module_declaration_span_includes_end_module():
    source = "module @app\n  export : run\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    module_decl = program.declarations[0]
    module_token = _token_by_kind(tokens, TokenKind.MODULE)
    end_module_token = _token_by_kind(tokens, TokenKind.END_MODULE)

    assert isinstance(module_decl, ModuleDeclaration)
    assert module_decl.span.start == module_token.span.start
    assert module_decl.span.end == end_module_token.span.end


def test_parser_import_declaration_span_includes_target_without_alias():
    source = (
        "module @app\n"
        "  import @math.utils\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    module_decl = program.declarations[0]
    import_decl = module_decl.items[0]
    import_token = _token_by_kind(tokens, TokenKind.IMPORT)
    target_token = _token_by_kind(tokens, TokenKind.QUALIFIED_MODULE_NAME, index=1)

    assert isinstance(import_decl, ImportDeclaration)
    assert import_decl.span.start == import_token.span.start
    assert import_decl.span.end == target_token.span.end


def test_parser_import_declaration_span_includes_alias_with_alias():
    source = (
        "module @app\n"
        "  import @math as m\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    module_decl = program.declarations[0]
    import_decl = module_decl.items[0]
    import_token = _token_by_kind(tokens, TokenKind.IMPORT)
    alias_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="m")

    assert isinstance(import_decl, ImportDeclaration)
    assert import_decl.span.start == import_token.span.start
    assert import_decl.span.end == alias_token.span.end


def test_parser_include_declaration_span_includes_path_literal():
    source = 'include "path.nic"\n'
    tokens = lex(source)
    program = parse_source_raw(source)
    include_decl = program.declarations[0]
    include_token = _token_by_kind(tokens, TokenKind.INCLUDE)
    path_token = _token_by_kind(tokens, TokenKind.STRING_LITERAL)

    assert isinstance(include_decl, IncludeDeclaration)
    assert include_decl.span.start == include_token.span.start
    assert include_decl.span.end == path_token.span.end


def test_parser_export_declaration_span_includes_exported_word_token():
    source = "module @app\n  export : run\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    module_decl = program.declarations[0]
    export_decl = module_decl.items[0]
    export_token = _token_by_kind(tokens, TokenKind.EXPORT)
    word_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="run")

    assert isinstance(module_decl, ModuleDeclaration)
    assert isinstance(export_decl, ExportDeclaration)
    assert export_decl.span.start == export_token.span.start
    assert export_decl.span.end == word_token.span.end


def test_parser_word_def_span_includes_terminating_semicolon():
    source = "module @app\n  : run { -- }\n    0\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    module_decl = program.declarations[0]
    word = module_decl.items[0]
    semicolon_token = _token_by_kind(tokens, TokenKind.SEMICOLON)

    assert isinstance(module_decl, ModuleDeclaration)
    assert word.name == "run"
    assert word.span.end == semicolon_token.span.end


def test_parser_word_def_span_starts_at_pub_modifier():
    source = "module @app\n  pub : run { -- }\n    0\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    word = program.declarations[0].items[0]
    pub_token = _token_by_kind(tokens, TokenKind.PUB)

    assert word.name == "run"
    assert word.span.start == pub_token.span.start


def test_parser_word_def_span_starts_at_dirty_modifier():
    source = "module @app\n  dirty : run { -- }\n    0\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    word = program.declarations[0].items[0]
    dirty_token = _token_by_kind(tokens, TokenKind.DIRTY)

    assert word.name == "run"
    assert word.span.start == dirty_token.span.start


def test_parser_word_def_span_starts_at_earliest_modifier_when_pub_and_dirty():
    source = "module @app\n  pub dirty : run { -- }\n    0\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    word = program.declarations[0].items[0]
    pub_token = _token_by_kind(tokens, TokenKind.PUB)
    semicolon_token = _token_by_kind(tokens, TokenKind.SEMICOLON)

    assert word.name == "run"
    assert word.span.start == pub_token.span.start
    assert word.span.end == semicolon_token.span.end


def test_parser_signature_span_includes_delimiters():
    source = "module @app\n  : run { a:Int -- b:Int }\n    a\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    signature = program.words[0].signature
    lbrace_token = _token_by_kind(tokens, TokenKind.LBRACE, index=0)
    rbrace_token = _token_by_kind(tokens, TokenKind.RBRACE, index=0)

    assert signature.span.start == lbrace_token.span.start
    assert signature.span.end == rbrace_token.span.end


def test_parser_parameter_span_starts_at_name_and_ends_at_type_end():
    source = "module @app\n  : run { xs:Map<String,Int> -- }\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    parameter = program.words[0].signature.inputs[0]
    name_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="xs")
    end_type_token = _token_by_kind(tokens, TokenKind.GT, index=0)

    assert parameter.span.start == name_token.span.start
    assert parameter.span.end == end_type_token.span.end
    assert parameter.span.end == parameter.type_node.span.end


def test_parser_type_span_includes_closing_generic_delimiter():
    source = "module @app\n  : run { -- m:Map<String,List<Int>> }\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    type_node = program.words[0].signature.outputs[0].type_node
    map_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="Map")
    outer_gt = _token_by_kind(tokens, TokenKind.GT, index=1)

    assert type_node.span.start == map_token.span.start
    assert type_node.span.end == outer_gt.span.end


def test_parser_quote_type_argument_preserves_nested_range_provenance():
    source = "module @app\n  : run { -- q:Quote<{ | x:Int -- y:Int }> }\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    type_node = program.words[0].signature.outputs[0].type_node
    quote_type = type_node.args[0]
    quote_name_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="Quote")
    quote_type_lbrace = _token_by_kind(tokens, TokenKind.LBRACE, index=1)
    quote_type_rbrace = _token_by_kind(tokens, TokenKind.RBRACE, index=0)
    gt_token = _token_by_kind(tokens, TokenKind.GT, index=0)

    assert type_node.span.start == quote_name_token.span.start
    assert type_node.span.end == gt_token.span.end
    assert quote_type.span.start == quote_type_lbrace.span.start
    assert quote_type.span.end == quote_type_rbrace.span.end


def test_parser_quote_type_span_includes_delimiters():
    source = (
        "module @app\n"
        "  : typed { -- q:Quote<{ | x:Int -- y:Int }> }\n"
        "    0 drop\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    quote_type = program.words[0].signature.outputs[0].type_node.args[0]
    quote_type_lbrace = _token_by_kind(tokens, TokenKind.LBRACE, index=1)
    quote_type_rbrace = _token_by_kind(tokens, TokenKind.RBRACE, index=0)

    assert quote_type.span.start == quote_type_lbrace.span.start
    assert quote_type.span.end == quote_type_rbrace.span.end


def test_parser_non_empty_list_literal_span_includes_closing_bracket():
    source = "module @app\n  : xs { -- ys:List<Int> }\n    [1, 2, 3]\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    list_node = program.words[0].body.items[0]
    lbracket_token = _token_by_kind(tokens, TokenKind.LBRACKET)
    rbracket_token = _token_by_kind(tokens, TokenKind.RBRACKET)

    assert isinstance(list_node, ListLiteralNode)
    assert list_node.span.start == lbracket_token.span.start
    assert list_node.span.end == rbracket_token.span.end


def test_parser_typed_empty_list_span_includes_full_type_annotation():
    source = "module @app\n  : xs { -- ys:List<Int> }\n    []:List<Int>\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    list_node = program.words[0].body.items[0]
    lbracket_token = _token_by_kind(tokens, TokenKind.LBRACKET)
    end_type_token = _token_by_kind(tokens, TokenKind.GT, index=1)

    assert isinstance(list_node, TypedEmptyListNode)
    assert list_node.span.start == lbracket_token.span.start
    assert list_node.span.end == end_type_token.span.end
    assert list_node.span.end == list_node.type_node.span.end


def test_parser_typed_empty_map_span_includes_full_type_annotation():
    source = "module @app\n  : m { -- out:Map<String,Int> }\n    map.empty:Map<String,Int>\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    map_node = program.words[0].body.items[0]
    map_empty_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="map.empty")
    end_type_token = _token_by_kind(tokens, TokenKind.GT, index=1)

    assert isinstance(map_node, TypedEmptyMapNode)
    assert map_node.span.start == map_empty_token.span.start
    assert map_node.span.end == end_type_token.span.end
    assert map_node.span.end == map_node.type_node.span.end


def test_parser_quote_node_span_includes_closing_delimiter():
    source = "module @app\n  : q { -- }\n    :[ | -- | 1 ;]\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    quote = program.words[0].body.items[0]
    quote_start_token = _token_by_kind(tokens, TokenKind.QUOTE_START)
    quote_end_token = _token_by_kind(tokens, TokenKind.QUOTE_END)

    assert isinstance(quote, QuoteNode)
    assert quote.span.start == quote_start_token.span.start
    assert quote.span.end == quote_end_token.span.end


def test_parser_nested_structures_preserve_outer_ranges():
    source = (
        "module @app\n"
        "  : q { -- q:Quote<{ | -- }> }\n"
        "    :[ | -- | [1, 2] drop ;]\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    word = program.words[0]
    signature = word.signature
    quote_type = signature.outputs[0].type_node.args[0]
    quote_node = word.body.items[0]

    signature_lbrace = _token_by_kind(tokens, TokenKind.LBRACE, index=0)
    signature_rbrace = _token_by_kind(tokens, TokenKind.RBRACE, index=1)
    quote_type_lbrace = _token_by_kind(tokens, TokenKind.LBRACE, index=1)
    quote_type_rbrace = _token_by_kind(tokens, TokenKind.RBRACE, index=0)
    quote_start_token = _token_by_kind(tokens, TokenKind.QUOTE_START)
    quote_end_token = _token_by_kind(tokens, TokenKind.QUOTE_END)

    assert signature.span.start == signature_lbrace.span.start
    assert signature.span.end == signature_rbrace.span.end
    assert quote_type.span.start == quote_type_lbrace.span.start
    assert quote_type.span.end == quote_type_rbrace.span.end
    assert quote_node.span.start == quote_start_token.span.start
    assert quote_node.span.end == quote_end_token.span.end


def test_parser_word_body_block_span_uses_first_and_last_items():
    source = "module @app\n  : run { -- }\n    1 2 +\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    word = program.words[0]
    first_item_token = _token_by_kind(tokens, TokenKind.INT_LITERAL, lexeme="1")
    last_item_token = _token_by_kind(tokens, TokenKind.OPERATOR, lexeme="+")

    assert isinstance(word.body, BlockNode)
    assert word.body.span.start == first_item_token.span.start
    assert word.body.span.end == last_item_token.span.end


def test_parser_empty_word_body_block_span_is_zero_length_at_semicolon_boundary():
    source = "module @app\n  : run { -- }\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    word = program.words[0]
    semicolon_token = _token_by_kind(tokens, TokenKind.SEMICOLON)

    assert isinstance(word.body, BlockNode)
    assert word.body.items == ()
    assert word.body.span.start == semicolon_token.span.start
    assert word.body.span.end == semicolon_token.span.start
    assert word.body.span.start == word.body.span.end


def test_parser_quote_body_block_span_uses_items_while_quote_node_keeps_delimiters():
    source = "module @app\n  : q { -- }\n    :[ | -- | x 1 + ;]\n  ;\nend-module\n"
    tokens = lex(source)
    program = parse_source_raw(source)
    quote = program.words[0].body.items[0]
    first_body_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="x")
    last_body_token = _token_by_kind(tokens, TokenKind.OPERATOR, lexeme="+")
    quote_start_token = _token_by_kind(tokens, TokenKind.QUOTE_START)
    quote_end_token = _token_by_kind(tokens, TokenKind.QUOTE_END)

    assert isinstance(quote, QuoteNode)
    assert isinstance(quote.body, BlockNode)
    assert quote.body.span.start == first_body_token.span.start
    assert quote.body.span.end == last_body_token.span.end
    assert quote.span.start == quote_start_token.span.start
    assert quote.span.end == quote_end_token.span.end


def test_parser_signature_and_quote_type_ranges_remain_delimiter_based():
    source = (
        "module @app\n"
        "  : typed { -- q:Quote<{ | x:Int -- y:Int }> }\n"
        "    0\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    word = program.words[0]
    signature = word.signature
    quote_type = signature.outputs[0].type_node.args[0]
    body_literal = _token_by_kind(tokens, TokenKind.INT_LITERAL, lexeme="0")
    signature_lbrace = _token_by_kind(tokens, TokenKind.LBRACE, index=0)
    signature_rbrace = _token_by_kind(tokens, TokenKind.RBRACE, index=1)
    quote_type_lbrace = _token_by_kind(tokens, TokenKind.LBRACE, index=1)
    quote_type_rbrace = _token_by_kind(tokens, TokenKind.RBRACE, index=0)

    assert signature.span.start == signature_lbrace.span.start
    assert signature.span.end == signature_rbrace.span.end
    assert quote_type.span.start == quote_type_lbrace.span.start
    assert quote_type.span.end == quote_type_rbrace.span.end
    assert word.body.span.start == body_literal.span.start
    assert word.body.span.end == body_literal.span.end


def test_parser_if_node_span_with_else_includes_end():
    source = (
        "module @app\n"
        "  : choose { x:Bool -- n:Int }\n"
        "    x if\n"
        "      1\n"
        "    else\n"
        "      2\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    if_node = program.words[0].body.items[1]
    if_token = _token_by_kind(tokens, TokenKind.IF)
    end_token = _token_by_kind(tokens, TokenKind.END, index=0)
    then_literal = _token_by_kind(tokens, TokenKind.INT_LITERAL, lexeme="1")
    else_literal = _token_by_kind(tokens, TokenKind.INT_LITERAL, lexeme="2")

    assert isinstance(if_node, IfNode)
    assert if_node.then_block.span.start == then_literal.span.start
    assert if_node.then_block.span.end == then_literal.span.end
    assert if_node.else_block.span.start == else_literal.span.start
    assert if_node.else_block.span.end == else_literal.span.end
    assert if_node.span.start == if_token.span.start
    assert if_node.span.end == end_token.span.end


def test_parser_if_without_else_remains_rejected():
    with pytest.raises(ParseError):
        parse_source(
            ": choose { x:Bool -- n:Int }\n"
            "  x if\n"
            "    1\n"
            "  end\n"
            ";"
        )


def test_parser_if_empty_then_block_keeps_block_empty_policy_and_if_span():
    source = (
        "module @app\n"
        "  : choose { x:Bool -- n:Int }\n"
        "    x if\n"
        "    else\n"
        "      2\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    if_node = program.words[0].body.items[1]
    if_token = _token_by_kind(tokens, TokenKind.IF, index=0)
    else_token = _token_by_kind(tokens, TokenKind.ELSE, index=0)
    end_token = _token_by_kind(tokens, TokenKind.END, index=0)
    else_literal = _token_by_kind(tokens, TokenKind.INT_LITERAL, lexeme="2")

    assert isinstance(if_node, IfNode)
    assert if_node.then_block.items == ()
    assert if_node.then_block.span.start == else_token.span.start
    assert if_node.then_block.span.end == else_token.span.start
    assert if_node.else_block.span.start == else_literal.span.start
    assert if_node.else_block.span.end == else_literal.span.end
    assert if_node.span.start == if_token.span.start
    assert if_node.span.end == end_token.span.end


def test_parser_nested_if_preserves_inner_and_outer_ranges():
    source = (
        "module @app\n"
        "  : nested { x:Bool y:Bool -- n:Int }\n"
        "    x if\n"
        "      y if\n"
        "        1\n"
        "      else\n"
        "        2\n"
        "      end\n"
        "    else\n"
        "      3\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    outer_if = program.words[0].body.items[1]
    inner_if = outer_if.then_block.items[1]
    outer_if_token = _token_by_kind(tokens, TokenKind.IF, index=0)
    inner_if_token = _token_by_kind(tokens, TokenKind.IF, index=1)
    inner_end_token = _token_by_kind(tokens, TokenKind.END, index=0)
    outer_end_token = _token_by_kind(tokens, TokenKind.END, index=1)

    assert isinstance(outer_if, IfNode)
    assert isinstance(inner_if, IfNode)
    assert inner_if.span.start == inner_if_token.span.start
    assert inner_if.span.end == inner_end_token.span.end
    assert outer_if.span.start == outer_if_token.span.start
    assert outer_if.span.end == outer_end_token.span.end


def test_parser_word_body_block_span_stays_body_derived_with_if_node_inside():
    source = (
        "module @app\n"
        "  : choose { x:Bool -- n:Int }\n"
        "    x\n"
        "    x if\n"
        "      1\n"
        "    else\n"
        "      2\n"
        "    end\n"
        "    9\n"
        "  ;\n"
        "end-module\n"
    )
    tokens = lex(source)
    program = parse_source_raw(source)
    word = program.words[0]
    first_item_token = _token_by_kind(tokens, TokenKind.IDENTIFIER, lexeme="x", index=1)
    last_item_token = _token_by_kind(tokens, TokenKind.INT_LITERAL, lexeme="9", index=0)
    if_node = next(item for item in word.body.items if isinstance(item, IfNode))
    if_token = _token_by_kind(tokens, TokenKind.IF, index=0)
    end_token = _token_by_kind(tokens, TokenKind.END, index=0)

    assert isinstance(if_node, IfNode)
    assert word.body.span.start == first_item_token.span.start
    assert word.body.span.end == last_item_token.span.end
    assert if_node.span.start == if_token.span.start
    assert if_node.span.end == end_token.span.end
