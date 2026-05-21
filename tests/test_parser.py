from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.ast_nodes import (
    CaseNode,
    IdentifierNode,
    IfNode,
    ListLiteralNode,
    LiteralKind,
    LiteralNode,
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
from nicole.lexer import lex
from nicole.parser import ParseError, Parser


def parse_source(source: str):
    return Parser(lex(source)).parse()


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


def test_parser_pub_and_export():
    program = parse_source(
        "pub : foo { -- } 1 ;\n"
        "export : bar { -- } 2 ;"
    )

    assert program.words[0].visibility is Visibility.PUB
    assert program.words[1].visibility is Visibility.EXPORT


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


def test_parser_accepts_export_dirty_word_definition():
    program = parse_source("export dirty : foo { -- } ;")

    assert program.words[0].name == "foo"
    assert program.words[0].visibility is Visibility.EXPORT
    assert program.words[0].is_dirty_annotation is True


@pytest.mark.parametrize(
    "source",
    [
        "dirty pub : foo { -- } ;",
        "dirty export : foo { -- } ;",
        ": dirty foo { -- } ;",
    ],
)
def test_parser_rejects_invalid_dirty_modifier_ordering(source):
    with pytest.raises(ParseError):
        parse_source(source)


def test_parser_rejects_export_inside_subword():
    with pytest.raises(ParseError, match="export is only allowed for top-level words"):
        parse_source(
            ": outer { -- }\n"
            "  export : inner { -- }\n"
            "  ;\n"
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


@pytest.mark.parametrize(
    "source",
    [
        ": host.log { -- } ;",
        "pub : host.log { -- } ;",
        "export : host.log { -- } ;",
    ],
)
def test_parser_rejects_host_word_definitions(source):
    with pytest.raises(ParseError, match=r"cannot define reserved namespace word"):
        parse_source(source)


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
        ": is-dirty { -- } ;\n"
        ": dirty.value { -- } ;"
    )

    assert program.words[0].name == "dirty_log"
    assert program.words[1].name == "is-dirty"
    assert program.words[2].name == "dirty.value"


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
