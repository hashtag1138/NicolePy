from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.checker import CheckerError, check_program
from nicole.host_abi import HostWord, host_contract_from_words
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.resolver import resolve
from nicole.signature_collector import collect_signatures
from nicole.standard_symbols import with_standard_symbols


def check_source(source: str):
    program = Parser(lex(source)).parse()
    symbols = collect_signatures(program)
    symbols = with_standard_symbols(symbols)
    resolved = resolve(program, symbols)
    return check_program(resolved, symbols)


def signature_from_source(source: str):
    return Parser(lex(source)).parse().words[0].signature


def check_source_with_host_contract(source: str, host_words):
    program = Parser(lex(source)).parse()
    symbols = collect_signatures(program)
    symbols = with_standard_symbols(symbols)
    contract = host_contract_from_words(host_words)
    resolved = resolve(program, symbols, host_contract=contract)
    return check_program(resolved, symbols)


def test_checker_accepts_simple_add():
    check_source(
        ": add { x:Int y:Int -- z:Int }\n"
        "  x y +\n"
        ";"
    )


def test_checker_accepts_host_word_with_matching_signature():
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    check_source_with_host_contract(
        ": main { msg:String -- }\n"
        "  msg host.log\n"
        ";",
        [HostWord(name="host.log", signature=host_signature)],
    )


def test_checker_rejects_host_word_with_wrong_input_type():
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    with pytest.raises(CheckerError):
        check_source_with_host_contract(
            ": main { n:Int -- }\n"
            "  n host.log\n"
            ";",
            [HostWord(name="host.log", signature=host_signature)],
        )


def test_checker_accepts_host_word_with_output():
    host_signature = signature_from_source(": hostsig { -- n:Int } ;")
    check_source_with_host_contract(
        ": main { -- n:Int }\n"
        "  host.random-int\n"
        ";",
        [HostWord(name="host.random-int", signature=host_signature)],
    )


def test_checker_rejects_obvious_type_mismatch():
    with pytest.raises(CheckerError):
        check_source(
            ': bad { x:Int -- y:Int }\n'
            '  x "hello" +\n'
            ";"
        )


def test_checker_rejects_stack_underflow():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Int -- y:Int }\n"
            "  +\n"
            ";"
        )


def test_checker_rejects_drop_at_word_start_even_with_inputs():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Int -- }\n"
            "  drop\n"
            ";"
        )


def test_checker_rejects_extra_final_value():
    with pytest.raises(CheckerError):
        check_source(
            ": weird { x:Int y:Int -- z:Int }\n"
            "  1\n"
            "  x y +\n"
            ";"
        )


def test_checker_accepts_valid_if():
    check_source(
        ": abs { x:Int -- y:Int }\n"
        "  x 0 < if\n"
        "    0 x -\n"
        "  else\n"
        "    x\n"
        "  end\n"
        ";"
    )


def test_checker_rejects_if_branch_type_mismatch():
    with pytest.raises(CheckerError):
        check_source(
            ': bad { x:Int -- y:Int }\n'
            '  x 0 < if\n'
            '    1\n'
            '  else\n'
            '    "hello"\n'
            '  end\n'
            ";"
        )


def test_checker_rejects_non_bool_if_condition():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Int -- y:Int }\n"
            "  x if\n"
            "    1\n"
            "  else\n"
            "    2\n"
            "  end\n"
            ";"
        )


def test_checker_accepts_simple_bool_case():
    check_source(
        ": choose { b:Bool -- n:Int }\n"
        "  b case\n"
        "    true => 1\n"
        "    false => 0\n"
        "  end\n"
        ";"
    )


def test_checker_case_consumes_scrutinee():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { b:Bool -- b2:Bool n:Int }\n"
            "  b case\n"
            "    true => 1\n"
            "    false => 0\n"
            "  end\n"
            ";"
        )


def test_checker_rejects_case_branch_arity_mismatch():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { b:Bool -- n:Int }\n"
            "  b case\n"
            "    true => 1\n"
            "    false => 1 2\n"
            "  end\n"
            ";"
        )


def test_checker_rejects_case_branch_type_mismatch():
    with pytest.raises(CheckerError):
        check_source(
            ': bad { b:Bool -- n:Int }\n'
            '  b case\n'
            '    true => 1\n'
            '    false => "no"\n'
            '  end\n'
            ";"
        )


def test_checker_case_ok_pattern_binds_local():
    check_source(
        ": unwrap { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        "    Ok(v) => v\n"
        "    Err(MissingKey) => 0\n"
        "  end\n"
        ";"
    )


def test_checker_drop_in_case_branch_uses_branch_stack():
    check_source(
        ": ignore-ok { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        "    Ok(v) => v drop 0\n"
        "    Err(MissingKey) => 0\n"
        "  end\n"
        ";"
    )


def test_checker_rejects_non_exhaustive_bool_case():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { b:Bool -- n:Int }\n"
            "  b case\n"
            "    true => 1\n"
            "  end\n"
            ";"
        )


def test_checker_accepts_exhaustive_bool_case():
    check_source(
        ": ok { b:Bool -- n:Int }\n"
        "  b case\n"
        "    true => 1\n"
        "    false => 0\n"
        "  end\n"
        ";"
    )


def test_checker_accepts_bool_case_with_wildcard():
    check_source(
        ": ok { b:Bool -- n:Int }\n"
        "  b case\n"
        "    true => 1\n"
        "    _ => 0\n"
        "  end\n"
        ";"
    )


def test_checker_rejects_non_exhaustive_result_map_error_case():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { r:Result<Int,MapError> -- n:Int }\n"
            "  r case\n"
            "    Ok(v) => v\n"
            "  end\n"
            ";"
        )


def test_checker_accepts_result_map_error_case_with_specific_err_variant():
    check_source(
        ": ok { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        "    Ok(v) => v\n"
        "    Err(MissingKey) => 0\n"
        "  end\n"
        ";"
    )


def test_checker_accepts_result_map_error_case_with_err_binding():
    check_source(
        ": ok { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        "    Ok(v) => v\n"
        "    Err(e) => 0\n"
        "  end\n"
        ";"
    )


def test_checker_rejects_missing_key_pattern_in_bool_case():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { b:Bool -- n:Int }\n"
            "  b case\n"
            "    MissingKey => 1\n"
            "    _ => 0\n"
            "  end\n"
            ";"
        )


def test_checker_rejects_missing_key_variant_for_list_error_result():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { r:Result<Int,ListError> -- n:Int }\n"
            "  r case\n"
            "    Ok(v) => v\n"
            "    Err(MissingKey) => 0\n"
            "  end\n"
            ";"
        )


def test_checker_rejects_out_of_bounds_variant_for_map_error_result():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { r:Result<Int,MapError> -- n:Int }\n"
            "  r case\n"
            "    Ok(v) => v\n"
            "    Err(OutOfBounds) => 0\n"
            "  end\n"
            ";"
        )


def test_checker_accepts_typed_empty_list_value():
    check_source(
        ": empty-list { -- xs:List<Int> }\n"
        "  []:List<Int>\n"
        ";"
    )


def test_checker_accepts_typed_empty_map_value():
    check_source(
        ": empty-map { -- m:Map<String,Int> }\n"
        "  map.empty:Map<String,Int>\n"
        ";"
    )


def test_checker_accepts_map_with_valid_string_key_type() -> None:
    check_source(
        ": ok { -- m:Map<String,Int> }\n"
        "  map.empty:Map<String,Int>\n"
        ";"
    )


def test_checker_accepts_map_with_valid_bool_key_type_and_nested_value() -> None:
    check_source(
        ": ok { -- m:Map<Bool,List<Int>> }\n"
        "  map.empty:Map<Bool,List<Int>>\n"
        ";"
    )


def test_checker_rejects_map_with_list_key_type() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        check_source(
            ": bad { -- m:Map<List<Int>,Int> }\n"
            "  map.empty:Map<List<Int>,Int>\n"
            ";"
        )


def test_checker_rejects_map_with_result_key_type() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        check_source(
            ": bad { -- m:Map<Result<Int,MapError>,Int> }\n"
            "  map.empty:Map<Result<Int,MapError>,Int>\n"
            ";"
        )


def test_checker_rejects_map_with_float_key_type() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        check_source(
            ": bad-float-key { -- m:Map<Float,Int> }\n"
            "  map.empty:Map<Float,Int>\n"
            ";"
        )


def test_checker_rejects_map_with_quote_key_type() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        check_source(
            ": bad-quote-key { -- m:Map<Quote<{ | -- }>,Int> }\n"
            "  map.empty:Map<Quote<{ | -- }>,Int>\n"
            ";"
        )


def test_checker_rejects_typed_empty_list_with_wrong_return_type():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- xs:List<String> }\n"
            "  []:List<Int>\n"
            ";"
        )


def test_checker_rejects_typed_empty_map_with_wrong_return_type():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- m:Map<String,String> }\n"
            "  map.empty:Map<String,Int>\n"
            ";"
        )


def test_checker_accepts_drop_after_typed_empty_list():
    check_source(
        ": ignore { -- }\n"
        "  []:List<Int> drop\n"
        ";"
    )


def test_checker_accepts_list_len_builtin():
    check_source(
        ": len { -- n:Int }\n"
        "  []:List<Int> list.len\n"
        ";"
    )


def test_checker_accepts_map_len_builtin():
    check_source(
        ": len { -- n:Int }\n"
        "  map.empty:Map<String,Int> map.len\n"
        ";"
    )


def test_checker_rejects_list_len_on_non_list():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- n:Int }\n"
            "  1 list.len\n"
            ";"
        )


def test_checker_rejects_map_len_on_non_map():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- n:Int }\n"
            "  1 map.len\n"
            ";"
        )


def test_checker_rejects_wrong_return_type_after_list_len():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- s:String }\n"
            "  []:List<Int> list.len\n"
            ";"
        )


def test_checker_accepts_map_contains_with_matching_key():
    check_source(
        ": ok { -- b:Bool }\n"
        '  map.empty:Map<String,Int>\n'
        '  "hello"\n'
        "  map.contains\n"
        ";"
    )


def test_checker_rejects_map_contains_with_wrong_key_type():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- b:Bool }\n"
            '  map.empty:Map<String,Int>\n'
            "  42\n"
            "  map.contains\n"
            ";"
        )


def test_checker_rejects_map_contains_with_non_map_input():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- b:Bool }\n"
            "  1\n"
            '  "hello"\n'
            "  map.contains\n"
            ";"
        )


def test_checker_accepts_result_is_ok_builtin():
    check_source(
        ": ok { -- b:Bool }\n"
        "  []:List<Int>\n"
        "  0\n"
        "  list.get\n"
        "  result.is-ok\n"
        ";"
    )


def test_checker_accepts_result_is_err_builtin():
    check_source(
        ": ok { -- b:Bool }\n"
        "  []:List<Int>\n"
        "  0\n"
        "  list.get\n"
        "  result.is-err\n"
        ";"
    )


def test_checker_accepts_result_unwrap_or_builtin():
    check_source(
        ": ok { -- n:Int }\n"
        "  []:List<Int>\n"
        "  0\n"
        "  list.get\n"
        "  42\n"
        "  result.unwrap-or\n"
        ";"
    )


def test_checker_accepts_ok_constructor_in_result_frame() -> None:
    check_source(
        ": ok { -- r:Result<Int,MapError> }\n"
        "  1\n"
        "  Ok!\n"
        ";"
    )


def test_checker_accepts_err_constructor_in_result_frame() -> None:
    check_source(
        ": err { e:MapError -- r:Result<Int,MapError> }\n"
        "  e\n"
        "  Err!\n"
        ";"
    )


def test_checker_accepts_propagate_with_matching_result_error_type() -> None:
    check_source(
        ": ok { -- r:Result<Int,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "k"\n'
        "  map.get\n"
        "  ?\n"
        "  1 +\n"
        "  Ok!\n"
        ";"
    )


def test_checker_accepts_propagate_inside_quotation_with_result_output() -> None:
    check_source(
        ": q { -- q:Quote<{ | -- r:Result<Int,MapError> }> }\n"
        "  :[ | -- r:Result<Int,MapError> |\n"
        "    map.empty:Map<String,Int>\n"
        '    "k"\n'
        "    map.get\n"
        "    ?\n"
        "    1 +\n"
        "    Ok!\n"
        "  ;]\n"
        ";"
    )


def test_checker_accepts_nested_propagate_in_valid_contexts() -> None:
    check_source(
        ": nested { -- r:Result<Int,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "a"\n'
        "  map.get\n"
        "  ?\n"
        "  map.empty:Map<String,Int>\n"
        '  "b"\n'
        "  map.get\n"
        "  ?\n"
        "  +\n"
        "  Ok!\n"
        ";"
    )


def test_checker_rejects_ok_constructor_with_wrong_value_type() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- r:Result<Int,MapError> }\n"
            '  "bad"\n'
            "  Ok!\n"
            ";"
        )


def test_checker_rejects_err_constructor_with_wrong_error_type() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { e:ListError -- r:Result<Int,MapError> }\n"
            "  e\n"
            "  Err!\n"
            ";"
        )


def test_checker_rejects_ok_constructor_in_non_result_frame() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- n:Int }\n"
            "  1\n"
            "  Ok!\n"
            ";"
        )


def test_checker_rejects_err_constructor_in_non_result_frame() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { e:MapError -- n:Int }\n"
            "  e\n"
            "  Err!\n"
            ";"
        )


def test_checker_accepts_list_concat_with_matching_item_types():
    check_source(
        ": xs { -- out:List<Int> }\n"
        "  []:List<Int>\n"
        "  []:List<Int>\n"
        "  list.concat\n"
        ";"
        )


def test_checker_accepts_list_filter_builtin() -> None:
    check_source(
        ": filter { -- xs:List<Int> }\n"
        "  []:List<Int>\n"
        "  :[ | x:Int -- keep:Bool | true ;]\n"
        "  list.filter\n"
        ";"
    )


def test_checker_rejects_result_unwrap_or_with_wrong_fallback_type() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- n:Int }\n"
            "  []:List<Int>\n"
            "  0\n"
            "  list.get\n"
            '  "fallback"\n'
            "  result.unwrap-or\n"
            ";"
        )


def test_checker_rejects_propagate_on_non_result_input() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- r:Result<Int,MapError> }\n"
            "  1\n"
            "  ?\n"
            "  Ok!\n"
            ";"
        )


def test_checker_rejects_propagate_with_non_result_frame_output() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- n:Int }\n"
            "  map.empty:Map<String,Int>\n"
            '  "k"\n'
            "  map.get\n"
            "  ?\n"
            ";"
        )


def test_checker_rejects_propagate_with_multiple_frame_outputs() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- a:Int b:Int }\n"
            "  map.empty:Map<String,Int>\n"
            '  "k"\n'
            "  map.get\n"
            "  ?\n"
            "  1 2\n"
            ";"
        )


def test_checker_rejects_propagate_with_mismatched_error_type() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- r:Result<Int,MapError> }\n"
            "  []:List<Int>\n"
            "  0\n"
            "  list.get\n"
            "  ?\n"
            "  Ok!\n"
            ";"
        )


def test_checker_rejects_propagate_inside_quotation_with_non_result_output() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- q:Quote<{ | -- n:Int }> }\n"
            "  :[ | -- n:Int |\n"
            "    map.empty:Map<String,Int>\n"
            '    "k"\n'
            "    map.get\n"
            "    ?\n"
            "  ;]\n"
            ";"
        )


def test_checker_rejects_propagate_inside_quotation_with_mismatched_error_type() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- q:Quote<{ | -- r:Result<Int,MapError> }> }\n"
            "  :[ | -- r:Result<Int,MapError> |\n"
            "    []:List<Int>\n"
            "    0\n"
            "    list.get\n"
            "    ?\n"
            "    Ok!\n"
            "  ;]\n"
            ";"
        )


def test_checker_rejects_list_filter_with_non_bool_quote_output() -> None:
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- xs:List<Int> }\n"
            "  []:List<Int>\n"
            "  :[ | x:Int -- keep:Int | x ;]\n"
            "  list.filter\n"
            ";"
        )


def test_checker_rejects_list_concat_with_mismatched_item_types():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- out:List<Int> }\n"
            "  []:List<Int>\n"
            "  []:List<String>\n"
            "  list.concat\n"
            ";"
        )


def test_checker_accepts_list_get_builtin():
    check_source(
        ": get { -- r:Result<Int,ListError> }\n"
        "  []:List<Int>\n"
        "  0\n"
        "  list.get\n"
        ";"
    )


def test_checker_rejects_list_get_with_non_int_index():
    with pytest.raises(CheckerError):
        check_source(
            ': bad { -- r:Result<Int,ListError> }\n'
            "  []:List<Int>\n"
            '  "zero"\n'
            "  list.get\n"
            ";"
        )


def test_checker_accepts_list_set_builtin():
    check_source(
        ": set { -- r:Result<List<Int>,ListError> }\n"
        "  []:List<Int>\n"
        "  0\n"
        "  1\n"
        "  list.set\n"
        ";"
    )


def test_checker_rejects_list_set_with_wrong_value_type():
    with pytest.raises(CheckerError):
        check_source(
            ': bad { -- r:Result<List<Int>,ListError> }\n'
            "  []:List<Int>\n"
            "  0\n"
            '  "x"\n'
            "  list.set\n"
            ";"
        )


def test_checker_rejects_list_set_with_non_int_index():
    with pytest.raises(CheckerError):
        check_source(
            ': bad { -- r:Result<List<Int>,ListError> }\n'
            "  []:List<Int>\n"
            '  "zero"\n'
            "  1\n"
            "  list.set\n"
            ";"
        )


def test_checker_rejects_list_set_with_non_list_input():
    with pytest.raises(CheckerError):
        check_source(
            ': bad { -- r:Result<List<Int>,ListError> }\n'
            "  1\n"
            "  0\n"
            "  2\n"
            "  list.set\n"
            ";"
        )


def test_checker_accepts_list_set_for_other_item_type():
    check_source(
        ": set { -- r:Result<List<String>,ListError> }\n"
        "  []:List<String>\n"
        "  0\n"
        '  "x"\n'
        "  list.set\n"
        ";"
    )


def test_checker_accepts_map_get_builtin():
    check_source(
        ": get { -- r:Result<Int,MapError> }\n"
        '  map.empty:Map<String,Int>\n'
        '  "hello"\n'
        "  map.get\n"
        ";"
    )


def test_checker_rejects_map_get_with_wrong_key_type():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- r:Result<Int,MapError> }\n"
            '  map.empty:Map<String,Int>\n'
            "  42\n"
            "  map.get\n"
            ";"
        )


def test_checker_rejects_map_get_with_non_map_input():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- r:Result<Int,MapError> }\n"
            "  1\n"
            '  "hello"\n'
            "  map.get\n"
            ";"
        )


def test_checker_accepts_map_set_builtin():
    check_source(
        ": set { -- m:Map<String,Int> }\n"
        '  map.empty:Map<String,Int>\n'
        '  "hello"\n'
        "  1\n"
        "  map.set\n"
        ";"
    )


def test_checker_rejects_map_set_with_wrong_value_type():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- m:Map<String,Int> }\n"
            '  map.empty:Map<String,Int>\n'
            '  "hello"\n'
            '  "wrong"\n'
            "  map.set\n"
            ";"
        )


def test_checker_rejects_map_set_with_non_map_input():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- m:Map<String,Int> }\n"
            '  "not-a-map"\n'
            '  "hello"\n'
            "  1\n"
            "  map.set\n"
            ";"
        )


def test_checker_rejects_map_set_with_wrong_key_type():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- m:Map<String,Int> }\n"
            '  map.empty:Map<String,Int>\n'
            "  42\n"
            "  1\n"
            "  map.set\n"
            ";"
        )


def test_checker_accepts_map_remove_builtin():
    check_source(
        ": remove { -- r:Result<Map<String,Int>,MapError> }\n"
        '  map.empty:Map<String,Int>\n'
        '  "hello"\n'
        "  map.remove\n"
        ";"
    )


def test_checker_rejects_map_remove_with_wrong_key_type():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- m:Map<String,Int> }\n"
            '  map.empty:Map<String,Int>\n'
            "  42\n"
            "  map.remove\n"
            ";"
        )


def test_checker_rejects_map_remove_with_non_map_input():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- r:Result<Map<String,Int>,MapError> }\n"
            '  "not-a-map"\n'
            '  "hello"\n'
            "  map.remove\n"
            ";"
        )


def test_checker_rejects_wrong_return_type_after_list_get():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- s:String }\n"
            "  []:List<Int>\n"
            "  0\n"
            "  list.get\n"
            ";"
        )


def test_checker_accepts_simple_quotation_value():
    check_source(
        ": make { -- q:Quote<{ | x:Int -- y:Int }> }\n"
        "  :[ | x:Int -- y:Int | x 1 + ;]\n"
        ";"
    )


def test_checker_accepts_quotation_with_capture():
    check_source(
        ": make { -- q:Quote<{ captured:Int | value:Int -- out:Int }> }\n"
        "  10\n"
        "  :[ captured:Int | value:Int -- out:Int | captured value + ;]\n"
        ";"
    )


def test_checker_accepts_quotation_capture_reusing_parent_local_name():
    check_source(
        ": add-offset { x:Int offset:Int -- y:Int }\n"
        "  offset\n"
        "  :[ offset:Int | value:Int -- out:Int | value offset + ;]\n"
        "  x\n"
        "  swap\n"
        "  call\n"
        ";"
    )


def test_checker_accepts_call_with_capture():
    check_source(
        ": add10 { x:Int -- y:Int }\n"
        "  x\n"
        "  10\n"
        "  :[ captured:Int | value:Int -- out:Int | captured value + ;]\n"
        "  call\n"
        ";"
    )


def test_checker_rejects_quotation_with_extra_return_value():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- q:Quote<{ | x:Int -- y:Int }> }\n"
            "  :[ | x:Int -- y:Int | x x ;]\n"
            ";"
        )


def test_checker_rejects_drop_at_start_of_quotation():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- q:Quote<{ | x:Int -- y:Int }> }\n"
            "  :[ | x:Int -- y:Int | drop x ;]\n"
            ";"
        )


def test_checker_rejects_call_with_wrong_input_order():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- out:Int }\n"
            '  "hello"\n'
            "  1\n"
            "  :[ | a:Int b:String -- out:Int | a ;]\n"
            "  call\n"
            ";"
        )


def test_checker_rejects_call_on_non_quotation():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- out:Int }\n"
            "  1\n"
            "  call\n"
            ";"
        )


def test_checker_accepts_dup():
    check_source(
        ": ok { x:Int -- a:Int b:Int }\n"
        "  x dup\n"
        ";"
    )


def test_checker_accepts_swap():
    check_source(
        ": ok { x:Int y:String -- a:String b:Int }\n"
        "  x y swap\n"
        ";"
    )


def test_checker_accepts_over():
    check_source(
        ": ok { x:Int y:String -- a:Int b:String c:Int }\n"
        "  x y over\n"
        ";"
    )


def test_checker_accepts_rot():
    check_source(
        ": ok { x:Int y:String z:Bool -- a:String b:Bool c:Int }\n"
        "  x y z rot\n"
        ";"
    )


@pytest.mark.parametrize("operator", ["dup", "swap", "over", "rot"])
def test_checker_rejects_stack_underflow_for_stack_primitive(operator):
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- }\n"
            f"  {operator}\n"
            ";"
        )


@pytest.mark.parametrize("operator", ["-", "*", "div", "mod"])
def test_checker_accepts_integer_arithmetic_primitives(operator):
    check_source(
        ": ok { x:Int y:Int -- z:Int }\n"
        f"  x y {operator}\n"
        ";"
    )


@pytest.mark.parametrize("operator", ["-", "*", "div", "mod"])
def test_checker_rejects_integer_arithmetic_with_wrong_type(operator):
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Int y:String -- z:Int }\n"
            f"  x y {operator}\n"
            ";"
        )


@pytest.mark.parametrize("operator", ["+.", "*.", "/."])
def test_checker_accepts_float_arithmetic_primitives(operator):
    check_source(
        ": ok { x:Float y:Float -- z:Float }\n"
        f"  x y {operator}\n"
        ";"
    )


def test_checker_rejects_float_arithmetic_with_mixed_types():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Int y:Float -- z:Float }\n"
            "  x y +.\n"
            ";"
        )


@pytest.mark.parametrize("operator", ["<", "<=", ">", ">="])
def test_checker_accepts_integer_comparisons(operator):
    check_source(
        ": ok { x:Int y:Int -- b:Bool }\n"
        f"  x y {operator}\n"
        ";"
    )


@pytest.mark.parametrize("operator", ["<", "<=", ">", ">="])
def test_checker_accepts_float_comparisons(operator):
    check_source(
        ": ok { x:Float y:Float -- b:Bool }\n"
        f"  x y {operator}\n"
        ";"
    )


@pytest.mark.parametrize("operator", ["<", "<=", ">", ">="])
def test_checker_rejects_non_int_order_comparisons(operator):
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:String y:String -- b:Bool }\n"
            f"  x y {operator}\n"
            ";"
        )


def test_checker_rejects_mixed_numeric_order_comparison():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Int y:Float -- b:Bool }\n"
            "  x y <\n"
            ";"
        )


@pytest.mark.parametrize("operator", ["=", "!="])
def test_checker_accepts_equality_for_same_types(operator):
    check_source(
        ": ok { x:String y:String -- b:Bool }\n"
        f"  x y {operator}\n"
        ";"
    )


@pytest.mark.parametrize("operator", ["=", "!="])
def test_checker_rejects_equality_for_different_types(operator):
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Int y:String -- b:Bool }\n"
            f"  x y {operator}\n"
            ";"
        )


@pytest.mark.parametrize("operator", ["and", "or"])
def test_checker_accepts_boolean_binary_primitives(operator):
    check_source(
        ": ok { x:Bool y:Bool -- z:Bool }\n"
        f"  x y {operator}\n"
        ";"
    )


@pytest.mark.parametrize("operator", ["and", "or"])
def test_checker_rejects_boolean_binary_primitives_with_wrong_type(operator):
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Bool y:Int -- z:Bool }\n"
            f"  x y {operator}\n"
            ";"
        )


def test_checker_accepts_not():
    check_source(
        ": ok { x:Bool -- y:Bool }\n"
        "  x not\n"
        ";"
    )


def test_checker_rejects_not_with_wrong_type():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { x:Int -- y:Bool }\n"
            "  x not\n"
            ";"
        )


def test_checker_rejects_not_with_underflow():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- y:Bool }\n"
            "  not\n"
            ";"
        )


def test_checker_accepts_non_empty_int_list_literal():
    check_source(
        ": ints { -- xs:List<Int> }\n"
        "  [1, 2]\n"
        ";"
    )


def test_checker_accepts_non_empty_string_list_literal():
    check_source(
        ': strings { -- xs:List<String> }\n'
        '  ["a", "b"]\n'
        ";"
    )


def test_checker_accepts_non_empty_bool_list_literal():
    check_source(
        ": bools { -- xs:List<Bool> }\n"
        "  [true, false]\n"
        ";"
    )


def test_checker_rejects_heterogeneous_list_literal():
    with pytest.raises(CheckerError):
        check_source(
            ': bad { -- xs:List<Int> }\n'
            '  [1, "x"]\n'
            ";"
        )


def test_checker_rejects_wrong_return_type_for_non_empty_list_literal():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- xs:List<String> }\n"
            "  [1, 2]\n"
            ";"
        )


def test_checker_accepts_drop_after_non_empty_list_literal():
    check_source(
        ": ok { -- }\n"
        "  [1, 2] drop\n"
        ";"
    )


def test_checker_accepts_list_map_int_to_int():
    check_source(
        ": inc-all { xs:List<Int> -- ys:List<Int> }\n"
        "  xs\n"
        "  :[ | x:Int -- y:Int | x 1 + ;]\n"
        "  list.map\n"
        ";"
    )


def test_checker_accepts_list_map_int_to_string():
    check_source(
        ": label-all { xs:List<Int> -- ys:List<String> }\n"
        "  xs\n"
        '  :[ | x:Int -- y:String | "ok" ;]\n'
        "  list.map\n"
        ";"
    )


def test_checker_accepts_list_fold_sum():
    check_source(
        ": sum { xs:List<Int> -- n:Int }\n"
        "  xs\n"
        "  0\n"
        "  :[ | acc:Int x:Int -- out:Int | acc x + ;]\n"
        "  list.fold\n"
        ";"
    )


def test_checker_accepts_list_reduce_int():
    check_source(
        ": reduce { xs:List<Int> -- n:Int }\n"
        "  xs\n"
        "  :[ | a:Int b:Int -- c:Int | a b + ;]\n"
        "  list.reduce\n"
        ";"
    )


def test_checker_rejects_list_reduce_on_provably_empty_list():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { -- n:Int }\n"
            "  []:List<Int>\n"
            "  :[ | a:Int b:Int -- c:Int |\n"
            "    a b +\n"
            "  ;]\n"
            "  list.reduce\n"
            ";"
        )


def test_checker_accepts_list_reduce_on_non_empty_list_literal():
    check_source(
        ": ok { -- n:Int }\n"
        "  [1, 2]\n"
        "  :[ | a:Int b:Int -- c:Int |\n"
        "    a b +\n"
        "  ;]\n"
        "  list.reduce\n"
        ";"
    )


def test_checker_rejects_list_map_with_incompatible_quotation_input():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { xs:List<Int> -- ys:List<Int> }\n"
            "  xs\n"
            '  :[ | x:String -- y:Int | 1 ;]\n'
            "  list.map\n"
            ";"
        )


def test_checker_rejects_list_map_with_two_outputs():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { xs:List<Int> -- ys:List<Int> }\n"
            "  xs\n"
            "  :[ | x:Int -- y:Int z:Int | x x ;]\n"
            "  list.map\n"
            ";"
        )


def test_checker_rejects_list_fold_with_incompatible_accumulator():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { xs:List<Int> -- n:Int }\n"
            "  xs\n"
            '  "zero"\n'
            '  :[ | acc:Int x:Int -- out:Int | acc x + ;]\n'
            "  list.fold\n"
            ";"
        )


def test_checker_rejects_list_reduce_with_incompatible_output():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { xs:List<Int> -- n:Int }\n"
            "  xs\n"
            '  :[ | a:Int b:Int -- c:String | "no" ;]\n'
            "  list.reduce\n"
            ";"
        )


def test_checker_rejects_list_map_with_non_quotation_argument():
    with pytest.raises(CheckerError):
        check_source(
            ": bad { xs:List<Int> -- ys:List<Int> }\n"
            "  xs\n"
            "  1\n"
            "  list.map\n"
            ";"
        )
