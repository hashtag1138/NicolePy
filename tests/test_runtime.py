from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.host_abi import HostWord, host_contract_from_words
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.pipeline import analyze_program
from nicole.resolver import ResolutionError
from nicole.runtime import (
    Err,
    Ok,
    RuntimeError,
    RuntimeHostBindings,
    RuntimeQuote,
    RuntimeStack,
    _execute_call,
    _execute_identifier,
    _execute_operator,
    run_export,
)


def signature_from_source(source: str):
    return Parser(lex(source)).parse().words[0].signature


def test_runtime_valid_host_call() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature)])

    seen: list[str] = []

    checked = analyze_program(
        "export : app.run { -- }\n"
        '  "hello" host.log\n'
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)})
    result = run_export(checked, "app.run", runtime)

    assert result is None
    assert seen == ["hello"]


def test_runtime_drop_underflow() -> None:
    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("drop", RuntimeStack())


def test_runtime_dup_underflow() -> None:
    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("dup", RuntimeStack())


def test_runtime_swap_underflow() -> None:
    stack = RuntimeStack()
    stack.push(1)

    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("swap", stack)


def test_runtime_missing_host_binding() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- }\n"
        '  "hello" host.log\n'
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({})
    with pytest.raises(RuntimeError, match="missing host binding: host.log"):
        run_export(checked, "app.run", runtime)


def test_runtime_host_callable_exception_is_normalized() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- }\n"
        '  "hello" host.log\n'
        ";",
        host_contract=host_contract,
    )

    def boom(msg: str) -> None:
        raise ValueError("boom")

    runtime = RuntimeHostBindings({"host.log": boom})
    with pytest.raises(RuntimeError, match="runtime host error: host.log"):
        run_export(checked, "app.run", runtime)


def test_runtime_missing_export() -> None:
    checked = analyze_program("export : app.run { -- n:Int }\n  1\n;")

    with pytest.raises(RuntimeError, match="missing export: missing.export"):
        run_export(checked, "missing.export", RuntimeHostBindings({}))


def test_runtime_wrong_arity() -> None:
    checked = analyze_program(
        "export : app.add { a:Int b:Int -- result:Int }\n"
        "  a b +\n"
        ";"
    )

    with pytest.raises(RuntimeError, match="wrong arity"):
        run_export(checked, "app.add", RuntimeHostBindings({}), 1)

    with pytest.raises(RuntimeError, match="wrong arity"):
        run_export(checked, "app.add", RuntimeHostBindings({}), 1, 2, 3)


def test_runtime_wrong_runtime_signature() -> None:
    host_signature = signature_from_source(": hostsig { -- n:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.random-int", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  host.random-int\n"
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.random-int": lambda: "not-an-int"})
    with pytest.raises(RuntimeError, match="wrong runtime signature"):
        run_export(checked, "app.run", runtime)


def test_runtime_typed_arithmetic_export() -> None:
    checked = analyze_program(
        "export : app.add { a:Int b:Int -- result:Int }\n"
        "  a b +\n"
        ";"
    )

    result = run_export(checked, "app.add", RuntimeHostBindings({}), 2, 3)

    assert result == 5


def test_runtime_division_by_zero_is_normalized() -> None:
    checked = analyze_program("export : app.run { -- n:Int }\n  1 0 div\n;")

    with pytest.raises(RuntimeError, match="runtime arithmetic error: div by zero"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_modulo_by_zero_is_normalized() -> None:
    checked = analyze_program("export : app.run { -- n:Int }\n  1 0 mod\n;")

    with pytest.raises(RuntimeError, match="runtime arithmetic error: mod by zero"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_float_division_by_zero_is_normalized() -> None:
    checked = analyze_program("export : app.run { -- n:Float }\n  1.0 0.0 /.\n;")

    with pytest.raises(RuntimeError, match="runtime arithmetic error: /\\. by zero"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_nicole_word_calling_host_word() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature)])

    seen: list[str] = []
    checked = analyze_program(
        ": log-it { msg:String -- }\n"
        "  msg host.log\n"
        ";\n"
        "export : app.run { -- }\n"
        '  "hello" log-it\n'
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)})
    run_export(checked, "app.run", runtime)

    assert seen == ["hello"]


def test_runtime_nested_nicole_word_calls() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature)])

    seen: list[str] = []
    checked = analyze_program(
        ": inner { msg:String -- }\n"
        "  msg host.log\n"
        ";\n"
        ": middle { msg:String -- }\n"
        "  msg inner\n"
        ";\n"
        "export : app.run { -- }\n"
        '  "hello" middle\n'
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)})
    run_export(checked, "app.run", runtime)

    assert seen == ["hello"]


def test_runtime_multiple_host_words() -> None:
    log_signature = signature_from_source(": hostlog { msg:String -- } ;")
    random_signature = signature_from_source(": hostrandom { -- n:Int } ;")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.log", signature=log_signature),
            HostWord(name="host.random-int", signature=random_signature),
        ]
    )

    seen: list[str] = []
    checked = analyze_program(
        "export : app.process { msg:String -- n:Int }\n"
        "  msg host.log\n"
        "  host.random-int\n"
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings(
        {
            "host.log": lambda msg: seen.append(msg),
            "host.random-int": lambda: 42,
        }
    )
    result = run_export(checked, "app.process", runtime, "hello")

    assert seen == ["hello"]
    assert result == 42


def test_runtime_scopes_with_same_nested_name_remain_distinct() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature)])

    seen: list[str] = []
    checked = analyze_program(
        ": alpha { -- }\n"
        "  : helper { -- }\n"
        '    "alpha" host.log\n'
        "  ;\n"
        "  helper\n"
        ";\n"
        ": beta { -- }\n"
        "  : helper { -- }\n"
        '    "beta" host.log\n'
        "  ;\n"
        "  helper\n"
        ";\n"
        "export : app.alpha { -- }\n"
        "  alpha\n"
        ";\n"
        "export : app.beta { -- }\n"
        "  beta\n"
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)})
    run_export(checked, "app.alpha", runtime)
    run_export(checked, "app.beta", runtime)

    assert seen == ["alpha", "beta"]


def test_runtime_host_multi_output() -> None:
    host_signature = signature_from_source(": hostpair { -- a:Int b:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature)])
    checked = analyze_program(
        "export : app.pair { -- a:Int b:Int }\n"
        "  host.pair\n"
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.pair": lambda: (1, 2)})
    result = run_export(checked, "app.pair", runtime)

    assert result == (1, 2)


def test_runtime_host_multi_output_wrong_tuple_size() -> None:
    host_signature = signature_from_source(": hostpair { -- a:Int b:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature)])
    checked = analyze_program(
        "export : app.pair { -- a:Int b:Int }\n"
        "  host.pair\n"
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.pair": lambda: (1,)})
    with pytest.raises(RuntimeError, match="wrong runtime signature"):
        run_export(checked, "app.pair", runtime)


def test_runtime_host_multi_output_wrong_element_type() -> None:
    host_signature = signature_from_source(": hostpair { -- a:Int b:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature)])
    checked = analyze_program(
        "export : app.pair { -- a:Int b:Int }\n"
        "  host.pair\n"
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.pair": lambda: (1, "bad")})
    with pytest.raises(RuntimeError, match="host output 'b'"):
        run_export(checked, "app.pair", runtime)


def test_runtime_if_true_executes_then_branch() -> None:
    checked = analyze_program(
        "export : app.run { -- }\n"
        "  true\n"
        "  if\n"
        '    "yes" host.log\n'
        "  else\n"
        '    "no" host.log\n'
        "  end\n"
        ";",
        host_contract=host_contract_from_words(
            [HostWord(name="host.log", signature=signature_from_source(": hostsig { msg:String -- } ;"))]
        ),
    )

    seen: list[str] = []
    run_export(checked, "app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}))
    assert seen == ["yes"]


def test_runtime_nested_if_in_nested_word() -> None:
    checked = analyze_program(
        ": inner { flag:Bool -- n:Int }\n"
        "  flag if\n"
        "    1\n"
        "  else\n"
        "    0\n"
        "  end\n"
        ";\n"
        "export : app.run { -- n:Int }\n"
        "  true\n"
        "  inner\n"
        ";"
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({}))
    assert result == 1


def test_runtime_case_bool_true_false_branches() -> None:
    checked = analyze_program(
        "export : app.choose { flag:Bool -- n:Int }\n"
        "  flag\n"
        "  case\n"
        "    true => 1\n"
        "    false => 2\n"
        "  end\n"
        ";\n"
    )

    assert run_export(checked, "app.choose", RuntimeHostBindings({}), True) == 1
    assert run_export(checked, "app.choose", RuntimeHostBindings({}), False) == 2


def test_runtime_case_produces_stack_output() -> None:
    checked = analyze_program(
        "export : app.choose { flag:Bool -- n:Int }\n"
        "  flag\n"
        "  case\n"
        "    true => 1\n"
        "    false => 2\n"
        "  end\n"
        ";\n"
    )

    assert run_export(checked, "app.choose", RuntimeHostBindings({}), True) == 1
    assert run_export(checked, "app.choose", RuntimeHostBindings({}), False) == 2


def test_runtime_case_can_call_nicole_word() -> None:
    host_contract = host_contract_from_words(
        [HostWord(name="host.log", signature=signature_from_source(": hostsig { msg:String -- } ;"))]
    )
    checked = analyze_program(
        ": log-yes { -- }\n"
        '  "yes" host.log\n'
        ";\n"
        "export : app.run { flag:Bool -- }\n"
        "  flag\n"
        "  case\n"
        "    true => log-yes\n"
        "    false => log-yes\n"
        "  end\n"
        ";",
        host_contract=host_contract,
    )

    seen: list[str] = []
    run_export(checked, "app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}), True)

    assert seen == ["yes"]


def test_runtime_nested_case() -> None:
    checked = analyze_program(
        "export : app.run { flag:Bool -- n:Int }\n"
        "  flag\n"
        "  case\n"
        "    true =>\n"
        "      false\n"
        "      case\n"
        "        true => 1\n"
        "        false => 2\n"
        "      end\n"
        "    false => 3\n"
        "  end\n"
        ";"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({}), True) == 2
    assert run_export(checked, "app.run", RuntimeHostBindings({}), False) == 3


def test_runtime_case_result_ok_binding() -> None:
    checked = analyze_program(
        "export : app.unwrap { r:Result<Int,MapError> -- n:Int }\n"
        "  r\n"
        "  case\n"
        "    Ok(v) => v\n"
        "    Err(MissingKey) => 0\n"
        "  end\n"
        ";"
    )

    assert run_export(checked, "app.unwrap", RuntimeHostBindings({}), Ok(42)) == 42


def test_runtime_case_result_err_missing_key_variant() -> None:
    checked = analyze_program(
        "export : app.unwrap { r:Result<Int,MapError> -- n:Int }\n"
        "  r\n"
        "  case\n"
        "    Ok(v) => v\n"
        "    Err(MissingKey) => 0\n"
        "  end\n"
        ";"
    )

    assert run_export(checked, "app.unwrap", RuntimeHostBindings({}), Err("MissingKey")) == 0


def test_runtime_case_result_err_out_of_bounds_variant() -> None:
    checked = analyze_program(
        "export : app.unwrap { r:Result<Int,ListError> -- n:Int }\n"
        "  r\n"
        "  case\n"
        "    Ok(v) => v\n"
        "    Err(OutOfBounds) => 0\n"
        "  end\n"
        ";"
    )

    assert run_export(checked, "app.unwrap", RuntimeHostBindings({}), Err("OutOfBounds")) == 0


def test_runtime_case_result_other_error_no_match() -> None:
    checked = analyze_program(
        "export : app.unwrap { r:Result<Int,MapError> -- n:Int }\n"
        "  r\n"
        "  case\n"
        "    Err(MissingKey) => 0\n"
        "    Ok(v) => v\n"
        "  end\n"
        ";"
    )

    with pytest.raises(RuntimeError, match="runtime case match failure"):
        run_export(checked, "app.unwrap", RuntimeHostBindings({}), Err("Other"))


def test_runtime_case_branch_local_binding_does_not_escape_branch_scope() -> None:
    host_signature = signature_from_source(": hostfetch { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.fetch", signature=host_signature)])

    with pytest.raises(ResolutionError):
        analyze_program(
            "export : app.run { -- n:Int }\n"
            "  host.fetch\n"
            "  case\n"
            "    Ok(v) => v\n"
            "    Err(MissingKey) => 0\n"
            "  end\n"
            "  v\n"
            ";",
            host_contract=host_contract,
        )


def test_runtime_case_err_binding_returns_runtime_error_value() -> None:
    fetch_signature = signature_from_source(": hostfetch { -- r:Result<Int,MapError> } ;")
    fallback_signature = signature_from_source(": hostfallback { -- e:MapError } ;")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.fetch", signature=fetch_signature),
            HostWord(name="host.fallback-error", signature=fallback_signature),
        ]
    )
    checked = analyze_program(
        "export : app.run { -- e:MapError }\n"
        "  host.fetch\n"
        "  case\n"
        "    Ok(v) => host.fallback-error\n"
        "    Err(e) => e\n"
        "  end\n"
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings(
        {
            "host.fetch": lambda: Err("MissingKey"),
            "host.fallback-error": lambda: "MissingKey",
        }
    )
    assert run_export(checked, "app.run", runtime) == "MissingKey"


def test_runtime_case_first_matching_branch_wins() -> None:
    checked = analyze_program(
        "export : app.choose { b:Bool -- n:Int }\n"
        "  b\n"
        "  case\n"
        "    _ => 10\n"
        "    true => 1\n"
        "    false => 2\n"
        "  end\n"
        ";"
    )

    # Wildcard comes first in source/AST order, so it must win.
    assert run_export(checked, "app.choose", RuntimeHostBindings({}), True) == 10


def test_runtime_quote_literal_returns_runtime_quote_value() -> None:
    checked = analyze_program(
        "export : app.run { -- q:Quote<{ | -- n:Int }> }\n"
        "  :[ | -- n:Int | 1 ;]\n"
        ";\n"
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({}))
    assert isinstance(result, RuntimeQuote)


def test_runtime_call_returns_literal() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  :[ | -- n:Int | 7 ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 7


def test_runtime_call_executes_arithmetic() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  :[ | -- n:Int | 1 2 + ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 3


def test_runtime_call_with_one_input() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  5\n"
        "  :[ | x:Int -- y:Int | x 1 + ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 6


def test_runtime_call_with_multiple_inputs() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  1 2\n"
        "  :[ | x:Int y:Int -- z:Int | x y + ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 3


def test_runtime_call_non_commutative_input_order() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  7 3\n"
        "  :[ | x:Int y:Int -- z:Int | x y - ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 4


def test_runtime_call_with_capture_end_to_end() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  5\n"
        "  10\n"
        "  :[ a:Int | x:Int -- y:Int | a x + ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 15


def test_runtime_call_capture_and_input_interaction() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  4\n"
        "  3\n"
        "  :[ k:Int | x:Int -- y:Int | x k * ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 12


def test_runtime_call_multiple_output_order() -> None:
    checked = analyze_program(
        "export : app.run { -- first:Int second:Int }\n"
        "  1 2\n"
        "  :[ | x:Int y:Int -- first:Int second:Int | y x ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == (2, 1)


def test_runtime_call_can_call_nicole_word() -> None:
    checked = analyze_program(
        ": plus-one { x:Int -- y:Int }\n"
        "  x 1 +\n"
        ";\n"
        "export : app.run { -- n:Int }\n"
        "  5\n"
        "  :[ | x:Int -- y:Int | x plus-one ;]\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 6


def test_runtime_call_can_call_host_word() -> None:
    host_signature = signature_from_source(": hostsig { n:Int -- out:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.inc", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  5\n"
        "  :[ | x:Int -- y:Int | x host.inc ;]\n"
        "  call\n"
        ";\n",
        host_contract=host_contract,
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({"host.inc": lambda n: n + 1})) == 6


def test_runtime_call_on_non_quote_is_controlled_error() -> None:
    stack = RuntimeStack()
    stack.push(123)

    with pytest.raises(RuntimeError, match="call expects runtime quotation"):
        _execute_call({}, stack, {}, RuntimeHostBindings({}))


def test_runtime_nested_quotes_are_not_auto_executed() -> None:
    checked = analyze_program(
        "export : app.run { -- q:Quote<{ | -- n:Int }> }\n"
        "  :[ | -- q:Quote<{ | -- n:Int }> | :[ | -- n:Int | 1 ;] ;]\n"
        "  call\n"
        ";\n"
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({}))
    assert isinstance(result, RuntimeQuote)


def test_runtime_nested_quote_executes_only_with_explicit_second_call() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  :[ | -- q:Quote<{ | -- n:Int }> | :[ | -- n:Int | 1 ;] ;]\n"
        "  call\n"
        "  call\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 1


def test_runtime_typed_empty_list_returns_empty_tuple() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  []:List<Int>\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == ()


def test_runtime_list_literal_returns_tuple_in_source_order() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  [1, 2, 3]\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == (1, 2, 3)


def test_runtime_list_literal_elements_evaluate_left_to_right() -> None:
    host_signature = signature_from_source(": hostnext { -- n:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.next", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  [host.next, host.next, host.next]\n"
        ";\n",
        host_contract=host_contract,
    )

    counter = {"value": 0}

    def next_value() -> int:
        counter["value"] += 1
        return counter["value"]

    assert run_export(checked, "app.run", RuntimeHostBindings({"host.next": next_value})) == (1, 2, 3)


def test_runtime_nested_list_literal_returns_nested_tuple() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<List<Int>> }\n"
        "  [[1, 2], [3, 4]]\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == ((1, 2), (3, 4))


def test_runtime_quotation_inside_list_is_preserved_not_executed() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<Quote<{ | -- n:Int }>> }\n"
        "  [:[ | -- n:Int | 1 ;]]\n"
        ";\n"
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({}))
    assert isinstance(result, tuple)
    assert len(result) == 1
    assert isinstance(result[0], RuntimeQuote)


def test_runtime_host_result_can_be_packed_into_list_literal() -> None:
    host_signature = signature_from_source(": hostnum { -- n:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.num", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  [host.num, 2]\n"
        ";\n",
        host_contract=host_contract,
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({"host.num": lambda: 1})) == (1, 2)


def test_runtime_list_literal_error_in_element_aborts_construction() -> None:
    host_signature = signature_from_source(": hostfail { -- n:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.fail", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  [1, host.fail, 3]\n"
        ";\n",
        host_contract=host_contract,
    )

    def fail() -> int:
        raise ValueError("boom")

    with pytest.raises(RuntimeError, match="runtime host error: host.fail"):
        run_export(checked, "app.run", RuntimeHostBindings({"host.fail": fail}))


def test_runtime_list_len_typed_empty_list_is_zero() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  []:List<Int>\n"
        "  list.len\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 0


def test_runtime_list_len_non_empty_list_literal() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  [1, 2, 3]\n"
        "  list.len\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 3


def test_runtime_list_len_nested_list_counts_top_level_only() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  [[1, 2], [3, 4], [5]]\n"
        "  list.len\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 3


def test_runtime_list_len_quotation_inside_list_counts_as_one() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  [:[ | -- n:Int | 1 ;], :[ | -- n:Int | 2 ;]]\n"
        "  list.len\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 2


def test_runtime_list_len_malformed_runtime_value_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  []:List<Int>\n"
        "  list.len\n"
        ";\n"
    )
    list_len_node = checked.program.words[0].body.items[1]
    stack = RuntimeStack()
    stack.push("not-a-list")

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.len input: expected List"):
        _execute_identifier(list_len_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_push_empty_list_appends_value() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  []:List<Int>\n"
        "  10\n"
        "  list.push\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == (10,)


def test_runtime_list_push_non_empty_list_appends_value() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  [1, 2]\n"
        "  3\n"
        "  list.push\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == (1, 2, 3)


def test_runtime_list_push_nested_tuple_is_preserved() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<List<Int>> }\n"
        "  [[1], [2]]\n"
        "  [3]\n"
        "  list.push\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == ((1,), (2,), (3,))


def test_runtime_list_push_runtime_quote_is_preserved() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<Quote<{ | -- n:Int }>> }\n"
        "  [:[ | -- n:Int | 1 ;]]\n"
        "  :[ | -- n:Int | 2 ;]\n"
        "  list.push\n"
        ";\n"
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({}))
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], RuntimeQuote)
    assert isinstance(result[1], RuntimeQuote)


def test_runtime_list_push_preserves_stored_ok_value() -> None:
    stored_ok = Ok(123)
    host_signature = signature_from_source(": hostok { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.ok", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- xs:List<Result<Int,MapError>> }\n"
        "  []:List<Result<Int,MapError>>\n"
        "  host.ok\n"
        "  list.push\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.ok": lambda: stored_ok}))
    assert result == (stored_ok,)
    assert result[0] is stored_ok


def test_runtime_list_push_preserves_stored_err_value() -> None:
    stored_err = Err("x")
    host_signature = signature_from_source(": hosterr { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.err", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- xs:List<Result<Int,MapError>> }\n"
        "  []:List<Result<Int,MapError>>\n"
        "  host.err\n"
        "  list.push\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.err": lambda: stored_err}))
    assert result == (stored_err,)
    assert result[0] is stored_err


def test_runtime_list_push_returns_new_tuple_value() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  [1, 2]\n"
        "  3\n"
        "  list.push\n"
        ";\n"
    )
    list_push_node = checked.program.words[0].body.items[2]
    original = (1, 2)
    stack = RuntimeStack()
    stack.push(original)
    stack.push(3)

    _execute_identifier(list_push_node, {}, stack, {}, RuntimeHostBindings({}))
    result = stack.pop()
    assert result == (1, 2, 3)
    assert result is not original


def test_runtime_list_push_malformed_runtime_value_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  []:List<Int>\n"
        "  10\n"
        "  list.push\n"
        ";\n"
    )
    list_push_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push("not-a-list")
    stack.push(10)

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.push list: expected List"):
        _execute_identifier(list_push_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_set_valid_replacement_returns_ok() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [10, 20, 30]\n"
        "  0\n"
        "  99\n"
        "  list.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Ok((99, 20, 30))


def test_runtime_list_set_replacement_in_middle_position() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [10, 20, 30]\n"
        "  1\n"
        "  99\n"
        "  list.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Ok((10, 99, 30))


def test_runtime_list_set_replacement_in_last_position() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [10, 20, 30]\n"
        "  2\n"
        "  99\n"
        "  list.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Ok((10, 20, 99))


def test_runtime_list_set_empty_list_returns_out_of_bounds() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  []:List<Int>\n"
        "  0\n"
        "  1\n"
        "  list.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_set_negative_index_returns_out_of_bounds() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [10, 20, 30]\n"
        "  0 1 -\n"
        "  99\n"
        "  list.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_set_index_equal_to_length_returns_out_of_bounds() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [10, 20, 30]\n"
        "  3\n"
        "  99\n"
        "  list.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_set_index_greater_than_length_returns_out_of_bounds() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [10, 20, 30]\n"
        "  4\n"
        "  99\n"
        "  list.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_set_nested_tuple_is_preserved() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<List<Int>>,ListError> }\n"
        "  [[1], [2], [3]]\n"
        "  1\n"
        "  [9]\n"
        "  list.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Ok(((1,), (9,), (3,)))


def test_runtime_list_set_runtime_quote_is_preserved() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Quote<{ | -- n:Int }>>,ListError> }\n"
        "  [:[ | -- n:Int | 1 ;], :[ | -- n:Int | 2 ;]]\n"
        "  1\n"
        "  :[ | -- n:Int | 3 ;]\n"
        "  list.set\n"
        ";\n"
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({}))
    assert isinstance(result, Ok)
    assert isinstance(result.value, tuple)
    assert len(result.value) == 2
    assert isinstance(result.value[0], RuntimeQuote)
    assert isinstance(result.value[1], RuntimeQuote)


def test_runtime_list_set_preserves_stored_ok_value() -> None:
    stored_ok = Ok(123)
    host_signature = signature_from_source(": hostok { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.ok", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Result<Int,MapError>>,ListError> }\n"
        "  [host.ok]\n"
        "  0\n"
        "  host.ok\n"
        "  list.set\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.ok": lambda: stored_ok}))
    assert isinstance(result, Ok)
    assert result.value == (stored_ok,)
    assert result.value[0] is stored_ok


def test_runtime_list_set_preserves_stored_err_value() -> None:
    stored_err = Err("x")
    host_signature = signature_from_source(": hosterr { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.err", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Result<Int,MapError>>,ListError> }\n"
        "  [host.err]\n"
        "  0\n"
        "  host.err\n"
        "  list.set\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.err": lambda: stored_err}))
    assert isinstance(result, Ok)
    assert result.value == (stored_err,)
    assert result.value[0] is stored_err


def test_runtime_list_set_returns_new_tuple_value() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [1, 2, 3]\n"
        "  1\n"
        "  9\n"
        "  list.set\n"
        ";\n"
    )
    list_set_node = checked.program.words[0].body.items[3]
    original = (1, 2, 3)
    stack = RuntimeStack()
    stack.push(original)
    stack.push(1)
    stack.push(9)

    _execute_identifier(list_set_node, {}, stack, {}, RuntimeHostBindings({}))
    result = stack.pop()
    assert isinstance(result, Ok)
    assert result.value == (1, 9, 3)
    assert result.value is not original


def test_runtime_list_set_malformed_runtime_list_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [1, 2, 3]\n"
        "  1\n"
        "  9\n"
        "  list.set\n"
        ";\n"
    )
    list_set_node = checked.program.words[0].body.items[3]
    stack = RuntimeStack()
    stack.push("not-a-list")
    stack.push(1)
    stack.push(9)

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.set list: expected List"):
        _execute_identifier(list_set_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_set_malformed_runtime_index_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [1, 2, 3]\n"
        "  1\n"
        "  9\n"
        "  list.set\n"
        ";\n"
    )
    list_set_node = checked.program.words[0].body.items[3]
    stack = RuntimeStack()
    stack.push((1, 2, 3))
    stack.push("not-an-int")
    stack.push(9)

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.set index: expected Int"):
        _execute_identifier(list_set_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_get_valid_index_zero_returns_ok() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30]\n"
        "  0\n"
        "  list.get\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Ok(10)


def test_runtime_list_get_valid_middle_index_returns_ok() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30]\n"
        "  1\n"
        "  list.get\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Ok(20)


def test_runtime_list_get_valid_last_index_returns_ok() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30]\n"
        "  2\n"
        "  list.get\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Ok(30)


def test_runtime_list_get_empty_list_access_returns_out_of_bounds() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  []:List<Int>\n"
        "  0\n"
        "  list.get\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_get_index_equal_to_length_returns_out_of_bounds() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30]\n"
        "  3\n"
        "  list.get\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_get_index_greater_than_length_returns_out_of_bounds() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30]\n"
        "  4\n"
        "  list.get\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_get_negative_index_returns_out_of_bounds() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30]\n"
        "  0 1 -\n"
        "  list.get\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_get_nested_tuple_returned_unchanged() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [[1, 2], [3, 4]]\n"
        "  0\n"
        "  list.get\n"
        ";\n"
    )
    list_get_node = checked.program.words[0].body.items[2]
    inner = (1, 2)
    stack = RuntimeStack()
    stack.push((inner, (3, 4)))
    stack.push(0)

    _execute_identifier(list_get_node, {}, stack, {}, RuntimeHostBindings({}))
    result = stack.pop()
    assert isinstance(result, Ok)
    assert result.value is inner


def test_runtime_list_get_runtime_quote_returned_unchanged() -> None:
    checked = analyze_program(
        "export : app.run { -- q:Quote<{ | -- n:Int }> }\n"
        "  :[ | -- n:Int | 1 ;]\n"
        ";\n"
    )
    quote_value = run_export(checked, "app.run", RuntimeHostBindings({}))
    assert isinstance(quote_value, RuntimeQuote)

    list_get_checked = analyze_program(
        "export : app.run { -- r:Result<Quote<{ | -- n:Int }>,ListError> }\n"
        "  [:[ | -- n:Int | 1 ;]]\n"
        "  0\n"
        "  list.get\n"
        ";\n"
    )
    list_get_node = list_get_checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push((quote_value,))
    stack.push(0)

    _execute_identifier(list_get_node, {}, stack, {}, RuntimeHostBindings({}))
    result = stack.pop()
    assert isinstance(result, Ok)
    assert result.value is quote_value
    assert isinstance(result.value, RuntimeQuote)


def test_runtime_list_get_malformed_index_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30]\n"
        "  0\n"
        "  list.get\n"
        ";\n"
    )
    list_get_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push((10, 20, 30))
    stack.push("not-an-int")

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.get index: expected Int"):
        _execute_identifier(list_get_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_get_malformed_list_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30]\n"
        "  0\n"
        "  list.get\n"
        ";\n"
    )
    list_get_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push("not-a-list")
    stack.push(0)

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.get list: expected List"):
        _execute_identifier(list_get_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_get_preserves_stored_ok_value() -> None:
    stored_ok = Ok(123)
    host_signature = signature_from_source(": hostok { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.ok", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Result<Int,MapError>,ListError> }\n"
        "  [host.ok]\n"
        "  0\n"
        "  list.get\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.ok": lambda: stored_ok}))
    assert isinstance(result, Ok)
    assert result.value is stored_ok
    assert result.value == stored_ok


def test_runtime_list_get_preserves_stored_err_value() -> None:
    stored_err = Err("x")
    host_signature = signature_from_source(": hosterr { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.err", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Result<Int,MapError>,ListError> }\n"
        "  [host.err]\n"
        "  0\n"
        "  list.get\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.err": lambda: stored_err}))
    assert isinstance(result, Ok)
    assert result.value is stored_err
    assert result.value == stored_err


def test_runtime_list_get_preserves_stored_tuple_identity() -> None:
    stored_tuple = (1, 2)
    host_signature = signature_from_source(": hosttuple { -- xs:List<Int> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.tuple", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,ListError> }\n"
        "  [host.tuple]\n"
        "  0\n"
        "  list.get\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.tuple": lambda: stored_tuple}))
    assert isinstance(result, Ok)
    assert result.value is stored_tuple
    assert result.value == stored_tuple


def test_runtime_unsupported_collection_builtin() -> None:
    checked = analyze_program(
        "export : app.run { -- ys:List<Int> }\n"
        "  [1, 2]\n"
        "  :[ | x:Int -- y:Int | x 1 + ;]\n"
        "  list.map\n"
        ";\n"
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_unsupported_collection_builtin_inside_quote_still_fails() -> None:
    checked = analyze_program(
        "export : app.run { -- ys:List<Int> }\n"
        "  :[ | -- ys:List<Int> |\n"
        "    [1, 2]\n"
        "    :[ | x:Int -- y:Int | x 1 + ;]\n"
        "    list.map\n"
        "  ;]\n"
        "  call\n"
        ";\n"
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_if_false_executes_else_branch() -> None:
    checked = analyze_program(
        "export : app.run { -- }\n"
        "  false\n"
        "  if\n"
        '    "yes" host.log\n'
        "  else\n"
        '    "no" host.log\n'
        "  end\n"
        ";",
        host_contract=host_contract_from_words(
            [HostWord(name="host.log", signature=signature_from_source(": hostsig { msg:String -- } ;"))]
        ),
    )

    seen: list[str] = []
    run_export(checked, "app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}))

    assert seen == ["no"]


def test_runtime_if_can_call_nicole_word() -> None:
    host_contract = host_contract_from_words(
        [HostWord(name="host.log", signature=signature_from_source(": hostsig { msg:String -- } ;"))]
    )
    checked = analyze_program(
        ": log-yes { -- }\n"
        '  "yes" host.log\n'
        ";\n"
        "export : app.run { flag:Bool -- }\n"
        "  flag if\n"
        "    log-yes\n"
        "  else\n"
        "    log-yes\n"
        "  end\n"
        ";",
        host_contract=host_contract,
    )

    seen: list[str] = []
    run_export(checked, "app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}), True)

    assert seen == ["yes"]


def test_runtime_if_can_produce_stack_output() -> None:
    checked = analyze_program(
        "export : app.choose { flag:Bool -- n:Int }\n"
        "  flag if\n"
        "    1\n"
        "  else\n"
        "    2\n"
        "  end\n"
        ";"
    )

    assert run_export(checked, "app.choose", RuntimeHostBindings({}), True) == 1
    assert run_export(checked, "app.choose", RuntimeHostBindings({}), False) == 2


def test_runtime_nested_if_simple() -> None:
    checked = analyze_program(
        "export : app.run { flag:Bool -- n:Int }\n"
        "  flag if\n"
        "    true if\n"
        "      1\n"
        "    else\n"
        "      2\n"
        "    end\n"
        "  else\n"
        "    3\n"
        "  end\n"
        ";"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({}), True) == 1
    assert run_export(checked, "app.run", RuntimeHostBindings({}), False) == 3
