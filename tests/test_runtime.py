from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.checker import CheckerError
from nicole.host_abi import HostABIError, HostEffect, HostWord, host_contract_from_words
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
    UNIT,
    _execute_call,
    _execute_identifier,
    _execute_operator,
    run_export,
)


def signature_from_source(source: str):
    return Parser(lex(source)).parse().words[0].signature


def test_runtime_valid_host_call() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

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


def test_runtime_over_underflow() -> None:
    stack = RuntimeStack()
    stack.push(1)

    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("over", stack)


def test_runtime_rot_underflow() -> None:
    stack = RuntimeStack()
    stack.push(1)
    stack.push(2)

    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("rot", stack)


def test_runtime_missing_host_binding() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])
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
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])
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
    host_contract = host_contract_from_words([HostWord(name="host.random-int", signature=host_signature, effect=HostEffect.PURE)])
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


def test_runtime_comparison_operators_execute() -> None:
    checked = analyze_program(
        "export : app.lt-int { -- b:Bool }\n"
        "  1 2 <\n"
        ";\n"
        "export : app.ge-float { -- b:Bool }\n"
        "  2.0 3.0 >=\n"
        ";\n"
        "export : app.eq { -- b:Bool }\n"
        "  3 3 =\n"
        ";\n"
        "export : app.ne { -- b:Bool }\n"
        "  3 4 !=\n"
        ";"
    )

    assert run_export(checked, "app.lt-int", RuntimeHostBindings({})) is True
    assert run_export(checked, "app.ge-float", RuntimeHostBindings({})) is False
    assert run_export(checked, "app.eq", RuntimeHostBindings({})) is True
    assert run_export(checked, "app.ne", RuntimeHostBindings({})) is True


def test_runtime_boolean_operators_execute() -> None:
    checked = analyze_program(
        "export : app.andv { -- b:Bool }\n"
        "  true false and\n"
        ";\n"
        "export : app.orv { -- b:Bool }\n"
        "  true false or\n"
        ";\n"
        "export : app.not-true { -- b:Bool }\n"
        "  true not\n"
        ";\n"
        "export : app.not-false { -- b:Bool }\n"
        "  false not\n"
        ";"
    )

    assert run_export(checked, "app.andv", RuntimeHostBindings({})) is False
    assert run_export(checked, "app.orv", RuntimeHostBindings({})) is True
    assert run_export(checked, "app.not-true", RuntimeHostBindings({})) is False
    assert run_export(checked, "app.not-false", RuntimeHostBindings({})) is True


def test_runtime_boolean_operators_reject_non_bool() -> None:
    stack = RuntimeStack()
    stack.push(1)
    stack.push(2)
    with pytest.raises(RuntimeError, match="expected Bool"):
        _execute_operator("and", stack)

    stack = RuntimeStack()
    stack.push(1)
    with pytest.raises(RuntimeError, match="expected Bool"):
        _execute_operator("not", stack)


def test_runtime_over_and_rot_execute() -> None:
    checked = analyze_program(
        "export : app.over { -- a:Int b:Int c:Int }\n"
        "  1 2 over\n"
        ";\n"
        "export : app.rot { -- a:Int b:Int c:Int }\n"
        "  1 2 3 rot\n"
        ";"
    )

    assert run_export(checked, "app.over", RuntimeHostBindings({})) == (1, 2, 1)
    assert run_export(checked, "app.rot", RuntimeHostBindings({})) == (2, 3, 1)


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
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

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
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

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
            HostWord(name="host.log", signature=log_signature, effect=HostEffect.PURE),
            HostWord(name="host.random-int", signature=random_signature, effect=HostEffect.PURE),
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
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

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
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature, effect=HostEffect.PURE)])
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
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature, effect=HostEffect.PURE)])
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
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.pair { -- a:Int b:Int }\n"
        "  host.pair\n"
        ";",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.pair": lambda: (1, "bad")})
    with pytest.raises(RuntimeError, match="host output 'b'"):
        run_export(checked, "app.pair", runtime)


def test_runtime_unit_input_and_output_accept_unit_sentinel() -> None:
    checked = analyze_program(
        "export : app.echo-unit { u:Unit -- v:Unit }\n"
        "  u\n"
        ";\n"
    )

    result = run_export(checked, "app.echo-unit", RuntimeHostBindings({}), UNIT)
    assert result is UNIT


def test_runtime_unit_input_rejects_non_unit_values() -> None:
    checked = analyze_program(
        "export : app.echo-unit { u:Unit -- v:Unit }\n"
        "  u\n"
        ";\n"
    )

    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "app.echo-unit", RuntimeHostBindings({}), 123)
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "app.echo-unit", RuntimeHostBindings({}), "abc")
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "app.echo-unit", RuntimeHostBindings({}), True)
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "app.echo-unit", RuntimeHostBindings({}), None)


def test_runtime_zero_output_and_unit_output_are_distinct() -> None:
    checked = analyze_program(
        "export : app.no-output { -- }\n"
        ";\n"
        "export : app.unit-output { -- u:Unit }\n"
        "  host.produce-unit\n"
        ";\n",
        host_contract=host_contract_from_words(
            [HostWord(name="host.produce-unit", signature=signature_from_source(": hostproduce { -- u:Unit } ;"), effect=HostEffect.PURE)]
        ),
    )

    runtime = RuntimeHostBindings({"host.produce-unit": lambda: UNIT})
    assert run_export(checked, "app.no-output", runtime) is None
    assert run_export(checked, "app.unit-output", runtime) is UNIT


def test_runtime_host_unit_boundaries() -> None:
    host_in_signature = signature_from_source(": hostconsume { u:Unit -- n:Int } ;")
    host_out_signature = signature_from_source(": hostproduce { -- u:Unit } ;")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.consume-unit", signature=host_in_signature, effect=HostEffect.PURE),
            HostWord(name="host.produce-unit", signature=host_out_signature, effect=HostEffect.PURE),
        ]
    )

    checked = analyze_program(
        "export : app.consume { -- n:Int }\n"
        "  host.produce-unit\n"
        "  host.consume-unit\n"
        ";\n"
        "export : app.direct-consume { u:Unit -- n:Int }\n"
        "  u host.consume-unit\n"
        ";\n",
        host_contract=host_contract,
    )

    runtime_ok = RuntimeHostBindings(
        {
            "host.produce-unit": lambda: UNIT,
            "host.consume-unit": lambda u: 7,
        }
    )
    assert run_export(checked, "app.consume", runtime_ok) == 7
    assert run_export(checked, "app.direct-consume", runtime_ok, UNIT) == 7

    runtime_bad_output = RuntimeHostBindings(
        {
            "host.produce-unit": lambda: None,
            "host.consume-unit": lambda u: 7,
        }
    )
    with pytest.raises(RuntimeError, match="host output 'u': expected Unit"):
        run_export(checked, "app.consume", runtime_bad_output)

    runtime_bad_output_2 = RuntimeHostBindings(
        {
            "host.produce-unit": lambda: 123,
            "host.consume-unit": lambda u: 7,
        }
    )
    with pytest.raises(RuntimeError, match="host output 'u': expected Unit"):
        run_export(checked, "app.consume", runtime_bad_output_2)

    runtime_bad_input = RuntimeHostBindings(
        {
            "host.produce-unit": lambda: None,
            "host.consume-unit": lambda u: 7,
        }
    )
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "app.direct-consume", runtime_bad_input, 123)
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "app.direct-consume", runtime_bad_input, None)


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
            [HostWord(name="host.log", signature=signature_from_source(": hostsig { msg:String -- } ;"), effect=HostEffect.PURE)]
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
        [HostWord(name="host.log", signature=signature_from_source(": hostsig { msg:String -- } ;"), effect=HostEffect.PURE)]
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


def test_runtime_propagate_ok_continues_execution() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "k" 41 map.set\n'
        '  "k" map.get\n'
        "  ?\n"
        "  1 +\n"
        "  Ok!\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Ok(42)


def test_runtime_propagate_err_returns_immediately() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "missing" map.get\n'
        "  ?\n"
        "  0 +\n"
        "  Ok!\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("MissingKey")


def test_runtime_propagate_is_frame_local_inside_quotation() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  map.empty:Map<String,Int>\n"
        "  :[ | m:Map<String,Int> -- r:Result<Int,MapError> |\n"
        '    m "missing" map.get\n'
        "    ?\n"
        "    1 +\n"
        "    Ok!\n"
        "  ;]\n"
        "  call\n"
        "  9 result.unwrap-or\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 9


def test_runtime_propagate_multiple_in_one_frame() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "a" 1 map.set\n'
        '  "a" map.get\n'
        "  ?\n"
        "  drop\n"
        "  map.empty:Map<String,Int>\n"
        '  "missing" map.get\n'
        "  ?\n"
        "  drop\n"
        "  100 Ok!\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("MissingKey")


def test_runtime_case_branch_local_binding_does_not_escape_branch_scope() -> None:
    host_signature = signature_from_source(": hostfetch { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.fetch", signature=host_signature, effect=HostEffect.PURE)])

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
            HostWord(name="host.fetch", signature=fetch_signature, effect=HostEffect.PURE),
            HostWord(name="host.fallback-error", signature=fallback_signature, effect=HostEffect.PURE),
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
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "export : app.run { -- q:Quote<{ | -- n:Int }> }\n"
            "  :[ | -- n:Int | 1 ;]\n"
            ";\n"
        )


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
    host_contract = host_contract_from_words([HostWord(name="host.inc", signature=host_signature, effect=HostEffect.PURE)])
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
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "export : app.run { -- q:Quote<{ | -- n:Int }> }\n"
            "  :[ | -- q:Quote<{ | -- n:Int }> | :[ | -- n:Int | 1 ;] ;]\n"
            "  call\n"
            ";\n"
        )


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
    host_contract = host_contract_from_words([HostWord(name="host.next", signature=host_signature, effect=HostEffect.PURE)])
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
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "export : app.run { -- xs:List<Quote<{ | -- n:Int }>> }\n"
            "  [:[ | -- n:Int | 1 ;]]\n"
            ";\n"
        )


def test_runtime_host_result_can_be_packed_into_list_literal() -> None:
    host_signature = signature_from_source(": hostnum { -- n:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.num", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- xs:List<Int> }\n"
        "  [host.num, 2]\n"
        ";\n",
        host_contract=host_contract,
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({"host.num": lambda: 1})) == (1, 2)


def test_runtime_list_literal_error_in_element_aborts_construction() -> None:
    host_signature = signature_from_source(": hostfail { -- n:Int } ;")
    host_contract = host_contract_from_words([HostWord(name="host.fail", signature=host_signature, effect=HostEffect.PURE)])
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


def test_runtime_list_is_empty_executes() -> None:
    checked = analyze_program(
        "export : app.empty { -- b:Bool }\n"
        "  []:List<Int> list.is-empty\n"
        ";\n"
        "export : app.non-empty { -- b:Bool }\n"
        "  [1] list.is-empty\n"
        ";\n"
    )

    assert run_export(checked, "app.empty", RuntimeHostBindings({})) is True
    assert run_export(checked, "app.non-empty", RuntimeHostBindings({})) is False


def test_runtime_list_first_and_last_execute() -> None:
    checked = analyze_program(
        "export : app.first { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30] list.first\n"
        ";\n"
        "export : app.last { -- r:Result<Int,ListError> }\n"
        "  [10, 20, 30] list.last\n"
        ";\n"
    )

    assert run_export(checked, "app.first", RuntimeHostBindings({})) == Ok(10)
    assert run_export(checked, "app.last", RuntimeHostBindings({})) == Ok(30)


def test_runtime_list_first_and_last_empty_return_out_of_bounds_error() -> None:
    checked = analyze_program(
        "export : app.first-empty { -- r:Result<Int,ListError> }\n"
        "  []:List<Int> list.first\n"
        ";\n"
        "export : app.last-empty { -- r:Result<Int,ListError> }\n"
        "  []:List<Int> list.last\n"
        ";\n"
    )

    assert run_export(checked, "app.first-empty", RuntimeHostBindings({})) == Err("OutOfBounds")
    assert run_export(checked, "app.last-empty", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_append_and_reverse_execute() -> None:
    checked = analyze_program(
        "export : app.append { -- xs:List<Int> }\n"
        "  [1, 2] 3 list.append\n"
        ";\n"
        "export : app.reverse { -- xs:List<Int> }\n"
        "  [1, 2, 3] list.reverse\n"
        ";\n"
    )

    assert run_export(checked, "app.append", RuntimeHostBindings({})) == (1, 2, 3)
    assert run_export(checked, "app.reverse", RuntimeHostBindings({})) == (3, 2, 1)


def test_runtime_list_push_is_not_available_in_v1_surface() -> None:
    with pytest.raises(ResolutionError, match="unresolved name"):
        analyze_program(
            "export : app.run { -- xs:List<Int> }\n"
            "  []:List<Int>\n"
            "  10\n"
            "  list.push\n"
            ";\n"
        )


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
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "export : app.run { -- r:Result<List<Quote<{ | -- n:Int }>>,ListError> }\n"
            "  [:[ | -- n:Int | 1 ;], :[ | -- n:Int | 2 ;]]\n"
            "  1\n"
            "  :[ | -- n:Int | 3 ;]\n"
            "  list.set\n"
            ";\n"
        )


def test_runtime_list_set_preserves_stored_ok_value() -> None:
    stored_ok = Ok(123)
    host_signature = signature_from_source(": hostok { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.ok", signature=host_signature, effect=HostEffect.PURE)])
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
    host_contract = host_contract_from_words([HostWord(name="host.err", signature=host_signature, effect=HostEffect.PURE)])
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
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "export : app.run { -- q:Quote<{ | -- n:Int }> }\n"
            "  :[ | -- n:Int | 1 ;]\n"
            ";\n"
        )


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
    host_contract = host_contract_from_words([HostWord(name="host.ok", signature=host_signature, effect=HostEffect.PURE)])
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
    host_contract = host_contract_from_words([HostWord(name="host.err", signature=host_signature, effect=HostEffect.PURE)])
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
    host_contract = host_contract_from_words([HostWord(name="host.tuple", signature=host_signature, effect=HostEffect.PURE)])
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


def test_runtime_map_empty_returns_empty_dict() -> None:
    checked = analyze_program(
        "export : app.run { -- m:Map<String,Int> }\n"
        "  map.empty:Map<String,Int>\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == {}


def test_runtime_map_get_int_key_returns_ok() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<Int,String> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<String,MapError> }\n"
        "  host.map\n"
        "  1\n"
        "  map.get\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {1: "one"}}))
    assert result == Ok("one")


def test_runtime_map_get_string_key_returns_ok() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<String,Int> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,MapError> }\n"
        "  host.map\n"
        '  "hello"\n'
        "  map.get\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {"hello": 7}}))
    assert result == Ok(7)


def test_runtime_map_get_bool_key_returns_ok() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<Bool,Int> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,MapError> }\n"
        "  host.map\n"
        "  true\n"
        "  map.get\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {True: 7}}))
    assert result == Ok(7)


def test_runtime_map_get_missing_key_returns_missing_key() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "missing"\n'
        "  map.get\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("MissingKey")


def test_runtime_map_get_nested_tuple_is_preserved() -> None:
    stored_tuple = (1, 2)
    host_signature = signature_from_source(": hostmap { -- m:Map<String,List<Int>> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,MapError> }\n"
        "  host.map\n"
        '  "pair"\n'
        "  map.get\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {"pair": stored_tuple}}))
    assert isinstance(result, Ok)
    assert result.value is stored_tuple
    assert result.value == stored_tuple


def test_runtime_map_get_runtime_quote_is_preserved() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<String,Quote<{ | -- n:Int }>> } ;")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])


def test_runtime_map_get_stored_ok_and_err_values_are_preserved() -> None:
    stored_ok = Ok(123)
    stored_err = Err("x")
    host_signature = signature_from_source(": hostmap { -- m:Map<String,Result<Int,MapError>> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Result<Int,MapError>,MapError> }\n"
        "  host.map\n"
        '  "ok"\n'
        "  map.get\n"
        ";\n",
        host_contract=host_contract,
    )

    result_ok = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {"ok": stored_ok, "err": stored_err}}))
    assert isinstance(result_ok, Ok)
    assert result_ok.value is stored_ok
    assert result_ok.value == stored_ok

    checked_err = analyze_program(
        "export : app.run { -- r:Result<Result<Int,MapError>,MapError> }\n"
        "  host.map\n"
        '  "err"\n'
        "  map.get\n"
        ";\n",
        host_contract=host_contract,
    )
    result_err = run_export(checked_err, "app.run", RuntimeHostBindings({"host.map": lambda: {"ok": stored_ok, "err": stored_err}}))
    assert isinstance(result_err, Ok)
    assert result_err.value is stored_err
    assert result_err.value == stored_err


def test_runtime_map_get_unsupported_list_key_raises_runtime_error() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            "export : app.run { -- r:Result<Int,MapError> }\n"
            "  map.empty:Map<List<Int>,Int>\n"
            "  [1]\n"
            "  map.get\n"
            ";\n"
        )


def test_runtime_map_get_unsupported_result_key_raises_runtime_error() -> None:
    host_signature = signature_from_source(": hostkey { -- k:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.key", signature=host_signature, effect=HostEffect.PURE)])
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            "export : app.run { -- r:Result<Int,MapError> }\n"
            "  map.empty:Map<Result<Int,MapError>,Int>\n"
            "  host.key\n"
            "  map.get\n"
            ";\n",
            host_contract=host_contract,
        )


def test_runtime_map_contains_existing_key_returns_true() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<String,Int> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- b:Bool }\n"
        "  host.map\n"
        '  "hello"\n'
        "  map.contains\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {"hello": 7}}))
    assert result is True


def test_runtime_map_contains_missing_key_returns_false() -> None:
    checked = analyze_program(
        "export : app.run { -- b:Bool }\n"
        "  map.empty:Map<String,Int>\n"
        '  "missing"\n'
        "  map.contains\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) is False


def test_runtime_map_contains_bool_key_returns_true() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<Bool,Int> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- b:Bool }\n"
        "  host.map\n"
        "  true\n"
        "  map.contains\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {True: 7}}))
    assert result is True


def test_runtime_map_contains_unsupported_quote_key_raises_runtime_error() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            "export : app.run { -- b:Bool }\n"
            "  map.empty:Map<Quote<{ | -- n:Int }>,Int>\n"
            "  :[ | -- n:Int | 1 ;]\n"
            "  map.contains\n"
            ";\n"
        )


def test_runtime_map_get_malformed_runtime_map_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Int,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "hello"\n'
        "  map.get\n"
        ";\n"
    )
    map_get_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push(["not-a-map"])
    stack.push("hello")

    with pytest.raises(RuntimeError, match="wrong runtime signature for map\\.get map: expected Map"):
        _execute_identifier(map_get_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_map_contains_malformed_runtime_map_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- b:Bool }\n"
        "  map.empty:Map<String,Int>\n"
        '  "hello"\n'
        "  map.contains\n"
        ";\n"
    )
    map_contains_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push(["not-a-map"])
    stack.push("hello")

    with pytest.raises(RuntimeError, match="wrong runtime signature for map\\.contains map: expected Map"):
        _execute_identifier(map_contains_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_map_set_inserts_new_int_key() -> None:
    checked = analyze_program(
        "export : app.run { -- m:Map<Int,String> }\n"
        "  map.empty:Map<Int,String>\n"
        "  1\n"
        '  "one"\n'
        "  map.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == {1: "one"}


def test_runtime_map_set_updates_existing_int_key() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<Int,String> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- m:Map<Int,String> }\n"
        "  host.map\n"
        "  1\n"
        '  "uno"\n'
        "  map.set\n"
        ";\n",
        host_contract=host_contract,
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {1: "one"}})) == {1: "uno"}


def test_runtime_map_set_string_key() -> None:
    checked = analyze_program(
        "export : app.run { -- m:Map<String,Int> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "hello"\n'
        "  7\n"
        "  map.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == {"hello": 7}


def test_runtime_map_set_bool_key() -> None:
    checked = analyze_program(
        "export : app.run { -- m:Map<Bool,Int> }\n"
        "  map.empty:Map<Bool,Int>\n"
        "  true\n"
        "  7\n"
        "  map.set\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == {True: 7}


def test_runtime_map_set_returns_new_dict_and_preserves_original() -> None:
    host_map = {1: "one"}
    host_signature = signature_from_source(": hostmap { -- m:Map<Int,String> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- m:Map<Int,String> }\n"
        "  host.map\n"
        "  2\n"
        '  "two"\n'
        "  map.set\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: host_map}))
    assert result == {1: "one", 2: "two"}
    assert result is not host_map
    assert host_map == {1: "one"}


def test_runtime_map_set_preserves_nested_tuple_value() -> None:
    stored_tuple = (1, 2)
    checked = analyze_program(
        "export : app.run { -- r:Result<List<Int>,MapError> }\n"
        "  map.empty:Map<String,List<Int>>\n"
        '  "pair"\n'
        "  [1, 2]\n"
        "  map.set\n"
        '  "pair"\n'
        "  map.get\n"
        ";\n"
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({}))
    assert result == Ok(stored_tuple)


def test_runtime_map_set_preserves_runtime_quote_value() -> None:
    host_signature = signature_from_source(": hostquote { -- q:Quote<{ | -- n:Int }> } ;")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.quote", signature=host_signature, effect=HostEffect.PURE)])


def test_runtime_map_set_preserves_stored_ok_and_err_values() -> None:
    stored_ok = Ok(123)
    stored_err = Err("x")
    ok_signature = signature_from_source(": hostok { -- r:Result<Int,MapError> } ;")
    err_signature = signature_from_source(": hosterr { -- r:Result<Int,MapError> } ;")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.ok", signature=ok_signature, effect=HostEffect.PURE),
            HostWord(name="host.err", signature=err_signature, effect=HostEffect.PURE),
        ]
    )

    checked_ok = analyze_program(
        "export : app.run { -- r:Result<Result<Int,MapError>,MapError> }\n"
        "  map.empty:Map<String,Result<Int,MapError>>\n"
        '  "ok"\n'
        "  host.ok\n"
        "  map.set\n"
        '  "ok"\n'
        "  map.get\n"
        ";\n",
        host_contract=host_contract,
    )
    result_ok = run_export(
        checked_ok,
        "app.run",
        RuntimeHostBindings({"host.ok": lambda: stored_ok, "host.err": lambda: stored_err}),
    )
    assert isinstance(result_ok, Ok)
    assert result_ok.value is stored_ok

    checked_err = analyze_program(
        "export : app.run { -- r:Result<Result<Int,MapError>,MapError> }\n"
        "  map.empty:Map<String,Result<Int,MapError>>\n"
        '  "err"\n'
        "  host.err\n"
        "  map.set\n"
        '  "err"\n'
        "  map.get\n"
        ";\n",
        host_contract=host_contract,
    )
    result_err = run_export(
        checked_err,
        "app.run",
        RuntimeHostBindings({"host.ok": lambda: stored_ok, "host.err": lambda: stored_err}),
    )
    assert isinstance(result_err, Ok)
    assert result_err.value is stored_err


def test_runtime_map_set_malformed_runtime_map_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- m:Map<String,Int> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "hello"\n'
        "  1\n"
        "  map.set\n"
        ";\n"
    )
    map_set_node = checked.program.words[0].body.items[3]
    stack = RuntimeStack()
    stack.push(["not-a-map"])
    stack.push("hello")
    stack.push(1)

    with pytest.raises(RuntimeError, match="wrong runtime signature for map\\.set map: expected Map"):
        _execute_identifier(map_set_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_map_set_unsupported_key_type_raises_runtime_error() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            "export : app.run { -- m:Map<List<Int>,Int> }\n"
            "  map.empty:Map<List<Int>,Int>\n"
            "  [1]\n"
            "  1\n"
            "  map.set\n"
            ";\n"
        )


def test_runtime_map_remove_existing_key_returns_ok_new_dict() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<Int,String> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Map<Int,String>,MapError> }\n"
        "  host.map\n"
        "  1\n"
        "  map.remove\n"
        ";\n",
        host_contract=host_contract,
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {1: "one", 2: "two"}})) == Ok({2: "two"})


def test_runtime_map_remove_missing_key_returns_missing_key() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Map<String,Int>,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "missing"\n'
        "  map.remove\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == Err("MissingKey")


def test_runtime_map_remove_returns_new_dict_and_preserves_original() -> None:
    host_map = {1: "one", 2: "two"}
    host_signature = signature_from_source(": hostmap { -- m:Map<Int,String> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Map<Int,String>,MapError> }\n"
        "  host.map\n"
        "  1\n"
        "  map.remove\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: host_map}))
    assert result == Ok({2: "two"})
    assert isinstance(result, Ok)
    assert result.value is not host_map
    assert host_map == {1: "one", 2: "two"}


def test_runtime_map_remove_string_key() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<String,Int> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Map<String,Int>,MapError> }\n"
        "  host.map\n"
        '  "hello"\n'
        "  map.remove\n"
        ";\n",
        host_contract=host_contract,
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {"hello": 7, "bye": 9}})) == Ok({"bye": 9})


def test_runtime_map_remove_bool_key() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<Bool,Int> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Map<Bool,Int>,MapError> }\n"
        "  host.map\n"
        "  true\n"
        "  map.remove\n"
        ";\n",
        host_contract=host_contract,
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({"host.map": lambda: {True: 7, False: 9}})) == Ok({False: 9})


def test_runtime_map_remove_preserves_remaining_nested_values() -> None:
    stored_tuple = (1, 2)
    host_signature = signature_from_source(": hostmap { -- m:Map<String,List<Int>> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        "export : app.run { -- r:Result<Map<String,List<Int>>,MapError> }\n"
        "  host.map\n"
        '  "drop"\n'
        "  map.remove\n"
        ";\n",
        host_contract=host_contract,
    )

    result = run_export(
        checked,
        "app.run",
        RuntimeHostBindings({"host.map": lambda: {"drop": (9,), "keep": stored_tuple}}),
    )
    assert isinstance(result, Ok)
    assert result.value == {"keep": stored_tuple}
    assert result.value["keep"] is stored_tuple


def test_runtime_map_remove_preserves_remaining_quote_values() -> None:
    host_signature = signature_from_source(": hostmap { -- m:Map<String,Quote<{ | -- n:Int }>> } ;")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])


def test_runtime_map_remove_malformed_runtime_map_is_controlled_error() -> None:
    checked = analyze_program(
        "export : app.run { -- r:Result<Map<String,Int>,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "hello"\n'
        "  map.remove\n"
        ";\n"
    )
    map_remove_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push(["not-a-map"])
    stack.push("hello")

    with pytest.raises(RuntimeError, match="wrong runtime signature for map\\.remove map: expected Map"):
        _execute_identifier(map_remove_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_map_remove_unsupported_key_type_raises_runtime_error() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            "export : app.run { -- r:Result<Map<List<Int>,Int>,MapError> }\n"
            "  map.empty:Map<List<Int>,Int>\n"
            "  [1]\n"
            "  map.remove\n"
            ";\n"
        )


def test_runtime_list_map_executes() -> None:
    checked = analyze_program(
        "export : app.run { -- ys:List<Int> }\n"
        "  [1, 2]\n"
        "  :[ | x:Int -- y:Int | x 1 + ;]\n"
        "  list.map\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == (2, 3)


def test_runtime_list_map_inside_quote_executes() -> None:
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

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == (2, 3)


def test_runtime_list_filter_executes() -> None:
    checked = analyze_program(
        "export : app.run { -- ys:List<Int> }\n"
        "  [1, 2, 3, 4]\n"
        "  :[ | x:Int -- keep:Bool | true ;]\n"
        "  list.filter\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == (1, 2, 3, 4)


def test_runtime_list_fold_executes() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  [1, 2, 3]\n"
        "  10\n"
        "  :[ | acc:Int x:Int -- out:Int | acc x + ;]\n"
        "  list.fold\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 16


def test_runtime_list_reduce_executes() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  [2, 3, 4]\n"
        "  :[ | a:Int b:Int -- c:Int | a b + ;]\n"
        "  list.reduce\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 9


def test_runtime_list_reduce_empty_from_host_is_runtime_error() -> None:
    host_signature = signature_from_source(": hostlist { -- xs:List<Int> } ;")
    host_contract = host_contract_from_words(
        [HostWord(name="host.list", signature=host_signature, effect=HostEffect.PURE)]
    )
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  host.list\n"
        "  :[ | a:Int b:Int -- c:Int | a b + ;]\n"
        "  list.reduce\n"
        ";\n",
        host_contract=host_contract,
    )

    with pytest.raises(RuntimeError, match="list.reduce cannot be applied to empty list at runtime"):
        run_export(checked, "app.run", RuntimeHostBindings({"host.list": lambda: ()}))


def test_runtime_list_map_with_nested_quote_executes() -> None:
    checked = analyze_program(
        "export : app.run { -- ys:List<Int> }\n"
        "  [1, 2]\n"
        "  :[ | x:Int -- y:Int |\n"
        "    x\n"
        "    :[ | n:Int -- m:Int | n 10 + ;]\n"
        "    call\n"
        "  ;]\n"
        "  list.map\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == (11, 12)


def test_runtime_result_is_ok_executes() -> None:
    checked = analyze_program(
        "export : app.run { -- b:Bool }\n"
        "  7 Ok!\n"
        "  result.is-ok\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) is True


def test_runtime_result_is_err_executes() -> None:
    checked = analyze_program(
        "export : app.run { -- b:Bool }\n"
        '  "x" Err!\n'
        "  result.is-err\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) is True


def test_runtime_err_constructor_preserves_generic_error_values() -> None:
    checked = analyze_program(
        "export : app.err-string { -- r:Result<Int,String> }\n"
        '  "abc" Err!\n'
        ";\n"
        "export : app.err-int { -- r:Result<Int,Int> }\n"
        "  123 Err!\n"
        ";\n"
        "export : app.err-bool { -- r:Result<Int,Bool> }\n"
        "  true Err!\n"
        ";\n"
        "export : app.err-list { -- r:Result<Int,List<String>> }\n"
        "  [\"x\", \"y\"] Err!\n"
        ";\n"
        "export : app.err-map { -- r:Result<Int,Map<String,Int>> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "k" 7 map.set\n'
        "  Err!\n"
        ";\n"
    )

    assert run_export(checked, "app.err-string", RuntimeHostBindings({})) == Err("abc")
    assert run_export(checked, "app.err-int", RuntimeHostBindings({})) == Err(123)
    assert run_export(checked, "app.err-bool", RuntimeHostBindings({})) == Err(True)
    assert run_export(checked, "app.err-list", RuntimeHostBindings({})) == Err(("x", "y"))
    assert run_export(checked, "app.err-map", RuntimeHostBindings({})) == Err({"k": 7})


def test_runtime_result_unwrap_or_executes() -> None:
    checked = analyze_program(
        "export : app.ok { -- n:Int }\n"
        "  [7]\n"
        "  0\n"
        "  list.get\n"
        "  9\n"
        "  result.unwrap-or\n"
        ";\n"
        "export : app.err { -- n:Int }\n"
        "  []:List<Int>\n"
        "  0\n"
        "  list.get\n"
        "  9\n"
        "  result.unwrap-or\n"
        ";\n"
    )

    assert run_export(checked, "app.ok", RuntimeHostBindings({})) == 7
    assert run_export(checked, "app.err", RuntimeHostBindings({})) == 9


def test_runtime_map_len_executes() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  map.empty:Map<String,Int>\n"
        '  "a" 1 map.set\n'
        '  "b" 2 map.set\n'
        "  map.len\n"
        ";\n"
    )

    assert run_export(checked, "app.run", RuntimeHostBindings({})) == 2


def test_runtime_map_is_empty_executes() -> None:
    checked = analyze_program(
        "export : app.empty { -- b:Bool }\n"
        "  map.empty:Map<String,Int> map.is-empty\n"
        ";\n"
        "export : app.non-empty { -- b:Bool }\n"
        "  map.empty:Map<String,Int> \"a\" 1 map.set map.is-empty\n"
        ";\n"
    )

    assert run_export(checked, "app.empty", RuntimeHostBindings({})) is True
    assert run_export(checked, "app.non-empty", RuntimeHostBindings({})) is False


def test_runtime_map_keys_and_values_preserve_insertion_order() -> None:
    checked = analyze_program(
        "export : app.keys { -- xs:List<String> }\n"
        "  map.empty:Map<String,Int>\n"
        "  \"a\" 1 map.set\n"
        "  \"b\" 2 map.set\n"
        "  map.keys\n"
        ";\n"
        "export : app.values { -- xs:List<Int> }\n"
        "  map.empty:Map<String,Int>\n"
        "  \"a\" 1 map.set\n"
        "  \"b\" 2 map.set\n"
        "  map.values\n"
        ";\n"
    )

    assert run_export(checked, "app.keys", RuntimeHostBindings({})) == ("a", "b")
    assert run_export(checked, "app.values", RuntimeHostBindings({})) == (1, 2)


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
            [HostWord(name="host.log", signature=signature_from_source(": hostsig { msg:String -- } ;"), effect=HostEffect.PURE)]
        ),
    )

    seen: list[str] = []
    run_export(checked, "app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}))

    assert seen == ["no"]


def test_runtime_if_can_call_nicole_word() -> None:
    host_contract = host_contract_from_words(
        [HostWord(name="host.log", signature=signature_from_source(": hostsig { msg:String -- } ;"), effect=HostEffect.PURE)]
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
