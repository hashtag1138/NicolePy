from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.host_abi import HostWord, host_contract_from_words
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.pipeline import analyze_program
from nicole.runtime import RuntimeError, RuntimeHostBindings, RuntimeStack, _execute_operator, run_export


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


def test_runtime_unsupported_if() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  1 0 < if\n"
        "    1\n"
        "  else\n"
        "    0\n"
        "  end\n"
        ";\n"
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported in phase 1"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_unsupported_if_in_nested_word() -> None:
    checked = analyze_program(
        ": inner { -- n:Int }\n"
        "  1 0 < if\n"
        "    1\n"
        "  else\n"
        "    0\n"
        "  end\n"
        ";\n"
        "export : app.run { -- n:Int }\n"
        "  inner\n"
        ";"
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported in phase 1"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_unsupported_case() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  1 case\n"
        "    0 => 0\n"
        "    _ => 1\n"
        "  end\n"
        ";\n"
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported in phase 1"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_unsupported_call() -> None:
    host_signature = signature_from_source(": hostsig { -- q:Quote<{ | -- }> } ;")
    host_contract = host_contract_from_words([HostWord(name="host.mkquote", signature=host_signature)])
    checked = analyze_program(
        "export : app.run { -- }\n"
        "  host.mkquote\n"
        "  call\n"
        ";\n",
        host_contract=host_contract,
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported in phase 1"):
        run_export(checked, "app.run", RuntimeHostBindings({"host.mkquote": lambda: object()}))


def test_runtime_unsupported_quote() -> None:
    checked = analyze_program(
        "export : app.run { -- q:Quote<{ | x:Int -- y:Int }> }\n"
        "  :[ | x:Int -- y:Int | x ;]\n"
        ";\n"
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported in phase 1"):
        run_export(checked, "app.run", RuntimeHostBindings({}))


def test_runtime_unsupported_collection_builtin() -> None:
    checked = analyze_program(
        "export : app.run { -- n:Int }\n"
        "  []:List<Int>\n"
        "  list.len\n"
        ";\n"
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported in phase 1"):
        run_export(checked, "app.run", RuntimeHostBindings({}))
