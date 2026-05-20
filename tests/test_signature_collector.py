from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.lexer import lex
from nicole.parser import Parser
from nicole.signature_collector import collect_signatures
from nicole.symbols import SymbolError, WordSymbol
from nicole.ast_nodes import Visibility


def parse_source(source: str):
    return Parser(lex(source)).parse()


def test_collect_simple_signature():
    program = parse_source(": add { a:Int b:Int -- r:Int } ;")
    table = collect_signatures(program)

    assert "add" in table.words
    symbol = table.words["add"][0]
    assert isinstance(symbol, WordSymbol)
    assert symbol.signature.inputs[0].name == "a"
    assert symbol.signature.outputs[0].name == "r"


def test_collect_mutual_recursion_support():
    program = parse_source(
        ": a { -- } b ;\n"
        ": b { -- } a ;"
    )
    table = collect_signatures(program)

    assert "a" in table.words
    assert "b" in table.words


def test_collect_rejects_same_name_with_different_input_types():
    program = parse_source(
        ": id { x:Int -- y:Int } ;\n"
        ": id { x:String -- y:String } ;"
    )

    with pytest.raises(SymbolError, match="duplicate visible name"):
        collect_signatures(program)


def test_collect_rejects_same_name_with_different_arities():
    program = parse_source(
        ": foo { a:Int b:Int -- r:Int } ;\n"
        ": foo { a:Int b:Int c:Int -- r:Int } ;"
    )

    with pytest.raises(SymbolError, match="duplicate visible name"):
        collect_signatures(program)


def test_collect_nested_subword_with_qualified_owner():
    program = parse_source(
        ": invoice { -- }\n"
        "  : subtotal { -- }\n"
        "  ;\n"
        ";"
    )
    table = collect_signatures(program)

    assert "invoice" in table.words
    assert "subtotal" in table.words
    symbol = table.words["subtotal"][0]
    assert symbol.owner == "invoice"
    assert symbol.name == "subtotal"
    assert symbol.qualified_name == "invoice.subtotal"


def test_collect_rejects_duplicate_sibling_subword_names():
    program = parse_source(
        ": parent { -- }\n"
        "  : child { -- n:Int } 1 ;\n"
        '  : child { -- text:String } "x" ;\n'
        ";"
    )

    with pytest.raises(SymbolError, match="duplicate visible name"):
        collect_signatures(program)


def test_collect_rejects_pub_export_name_collision():
    program = parse_source(
        "pub : foo { -- n:Int } 1 ;\n"
        "export : foo { -- n:Int } 2 ;"
    )

    with pytest.raises(SymbolError, match="duplicate visible name"):
        collect_signatures(program)


def test_collect_rejects_duplicate_export_names():
    program = parse_source(
        "export : entry { -- n:Int } 1 ;\n"
        'export : entry { -- text:String } "hello" ;'
    )

    with pytest.raises(SymbolError, match="duplicate visible name"):
        collect_signatures(program)


def test_collect_export_visibility_preserved():
    program = parse_source("export : entry { -- } ;")
    table = collect_signatures(program)

    symbol = table.words["entry"][0]
    assert symbol.visibility is Visibility.EXPORT


def test_collect_rejects_top_level_then_subword_same_name():
    program = parse_source(
        ": print { -- } ;\n"
        ": outer { -- }\n"
        "  : print { -- } ;\n"
        ";"
    )

    with pytest.raises(SymbolError, match="duplicate visible name"):
        collect_signatures(program)


def test_collect_rejects_subword_then_top_level_same_name():
    program = parse_source(
        ": outer { -- }\n"
        "  : helper { -- } ;\n"
        ";\n"
        ": helper { -- } ;"
    )

    with pytest.raises(SymbolError, match="duplicate visible name"):
        collect_signatures(program)


def test_collect_accepts_unique_private_subword_name():
    program = parse_source(
        ": helper { -- } ;\n"
        ": outer { -- }\n"
        "  : inner-helper { -- } ;\n"
        ";"
    )
    table = collect_signatures(program)

    assert "helper" in table.words
    assert "inner-helper" in table.words
