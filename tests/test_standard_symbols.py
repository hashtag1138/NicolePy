from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.lexer import lex
from nicole.parser import Parser
from nicole.signature_collector import collect_signatures
from nicole.standard_symbols import StandardSymbolError, load_standard_symbols, with_standard_symbols
from nicole.symbols import SymbolSource, WordSymbol


def parse_source(source: str):
    return Parser(lex(source)).parse()


def test_load_standard_symbols_contains_all_v1_builtins():
    builtins = load_standard_symbols()
    names = {symbol.name for symbol in builtins}

    assert names == {
        "result.is-ok",
        "result.is-err",
        "result.unwrap-or",
        "list.len",
        "list.get",
        "list.set",
        "list.concat",
        "list.map",
        "list.filter",
        "list.fold",
        "list.reduce",
        "map.get",
        "map.contains",
        "map.set",
        "map.remove",
        "map.len",
    }


def test_map_empty_is_not_a_standard_builtin_name():
    names = {symbol.name for symbol in load_standard_symbols()}

    assert "map.empty" not in names


def test_every_standard_builtin_is_word_symbol_with_builtin_source():
    builtins = load_standard_symbols()

    assert builtins
    assert all(isinstance(symbol, WordSymbol) for symbol in builtins)
    assert all(symbol.source is SymbolSource.BUILTIN for symbol in builtins)


def test_list_get_signature_shape():
    symbol = next(symbol for symbol in load_standard_symbols() if symbol.name == "list.get")

    assert len(symbol.signature.inputs) == 2
    assert len(symbol.signature.outputs) == 1


def test_list_set_signature_shape() -> None:
    symbol = next(symbol for symbol in load_standard_symbols() if symbol.name == "list.set")

    assert len(symbol.signature.inputs) == 3
    assert symbol.signature.inputs[0].type_node.name == "List"
    assert symbol.signature.inputs[1].type_node.name == "Int"
    assert symbol.signature.inputs[2].type_node.name == "T"
    assert len(symbol.signature.outputs) == 1
    assert symbol.signature.outputs[0].type_node.name == "Result"
    value_type, error_type = symbol.signature.outputs[0].type_node.args
    assert value_type.name == "List"
    assert error_type.name == "ListError"


def test_map_get_signature_shape():
    symbol = next(symbol for symbol in load_standard_symbols() if symbol.name == "map.get")

    assert len(symbol.signature.inputs) == 2
    assert len(symbol.signature.outputs) == 1


def test_map_contains_signature_shape() -> None:
    symbol = next(symbol for symbol in load_standard_symbols() if symbol.name == "map.contains")

    assert len(symbol.signature.inputs) == 2
    assert len(symbol.signature.outputs) == 1
    assert symbol.signature.outputs[0].type_node.name == "Bool"


def test_map_set_signature_shape() -> None:
    symbol = next(symbol for symbol in load_standard_symbols() if symbol.name == "map.set")

    assert len(symbol.signature.inputs) == 3
    assert len(symbol.signature.outputs) == 1
    assert symbol.signature.outputs[0].type_node.name == "Map"


def test_map_remove_signature_shape() -> None:
    symbol = next(symbol for symbol in load_standard_symbols() if symbol.name == "map.remove")

    assert len(symbol.signature.inputs) == 2
    assert len(symbol.signature.outputs) == 1
    result_type = symbol.signature.outputs[0].type_node
    assert result_type.name == "Result"
    assert result_type.args[0].name == "Map"
    assert result_type.args[1].name == "MapError"


def test_result_constructor_words_are_not_standard_builtins():
    names = {symbol.name for symbol in load_standard_symbols()}

    assert "Ok!" not in names
    assert "Err!" not in names


def test_result_helper_signature_shapes() -> None:
    builtins = {symbol.name: symbol for symbol in load_standard_symbols()}

    is_ok = builtins["result.is-ok"]
    assert len(is_ok.signature.inputs) == 1
    assert is_ok.signature.inputs[0].type_node.name == "Result"
    assert len(is_ok.signature.outputs) == 1
    assert is_ok.signature.outputs[0].type_node.name == "Bool"

    is_err = builtins["result.is-err"]
    assert len(is_err.signature.inputs) == 1
    assert is_err.signature.inputs[0].type_node.name == "Result"
    assert len(is_err.signature.outputs) == 1
    assert is_err.signature.outputs[0].type_node.name == "Bool"

    unwrap_or = builtins["result.unwrap-or"]
    assert len(unwrap_or.signature.inputs) == 2
    assert unwrap_or.signature.inputs[0].type_node.name == "Result"
    assert unwrap_or.signature.inputs[1].type_node.name == "T"
    assert len(unwrap_or.signature.outputs) == 1
    assert unwrap_or.signature.outputs[0].type_node.name == "T"


def test_non_v1_builtins_are_not_in_standard_symbol_inventory() -> None:
    names = {symbol.name for symbol in load_standard_symbols()}

    assert "list.push" not in names
    assert "list.pop" not in names
    assert "list.contains" not in names
    assert "map.keys" not in names
    assert "map.values" not in names
    assert "map.items" not in names


def test_higher_order_builtins_are_marked_callable_only_for_quotes():
    builtins = {symbol.name: symbol for symbol in load_standard_symbols()}

    assert builtins["list.map"].quote_callable_only is True
    assert builtins["list.filter"].quote_callable_only is True
    assert builtins["list.fold"].quote_callable_only is True
    assert builtins["list.reduce"].quote_callable_only is True
    assert builtins["list.get"].quote_callable_only is False


def test_injection_rejects_user_redefinition_of_builtin():
    program = parse_source(": list.get { -- } ;")
    table = collect_signatures(program)

    with pytest.raises(StandardSymbolError, match=r"cannot redefine standard builtin: list\.get"):
        with_standard_symbols(table)
