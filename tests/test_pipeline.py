from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.checker import CheckerError
from nicole.host_abi import BindingAvailability, HostABIError, HostEffect, HostWord, host_contract_from_words
from nicole.pipeline import CheckedProgram, analyze_program
from nicole.resolver import ResolutionError
from nicole.parser import ParseError, Parser
from nicole.lexer import lex


def signature_from_source(source: str):
    return Parser(lex(source)).parse().words[0].signature


def test_pipeline_accepts_program_without_export_or_host() -> None:
    result = analyze_program(
        ": main { -- n:Int }\n"
        "  1\n"
        ";"
    )

    assert isinstance(result, CheckedProgram)
    assert dict(result.export_contract.words) == {}


def test_pipeline_collects_simple_export() -> None:
    result = analyze_program(
        "export : main { -- n:Int }\n"
        "  1\n"
        ";"
    )

    assert "main" in result.export_contract.words
    assert result.export_contract.words["main"].signature is result.symbols.words["main"][0].signature


def test_pipeline_rejects_export_inside_subword() -> None:
    with pytest.raises(ParseError):
        analyze_program(
            ": outer { -- }\n"
            "  export : inner { -- }\n"
            "  ;\n"
            ";"
        )


@pytest.mark.parametrize(
    "source",
    [
        ": call { -- } ;",
        ": MissingKey { -- } ;",
        ": OutOfBounds { -- } ;",
        ": result.custom { -- } ;",
        ": list.custom { -- } ;",
        ": map.custom { -- } ;",
    ],
)
def test_pipeline_rejects_reserved_top_level_user_word_names(source: str) -> None:
    with pytest.raises(ParseError):
        analyze_program(source)


@pytest.mark.parametrize(
    "nested_name",
    ["call", "result.custom", "list.custom", "map.custom"],
)
def test_pipeline_rejects_reserved_subword_names(nested_name: str) -> None:
    with pytest.raises(ParseError):
        analyze_program(
            ": outer { -- }\n"
            f"  : {nested_name} {{ -- }} ;\n"
            ";"
        )


def test_pipeline_accepts_export_with_valid_host_contract() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

    result = analyze_program(
        "export : send { msg:String -- }\n"
        "  msg host.log\n"
        ";",
        host_contract=host_contract,
    )

    assert "send" in result.export_contract.words


def test_pipeline_rejects_missing_host_contract_entry() -> None:
    with pytest.raises(ResolutionError):
        analyze_program(
            "export : send { msg:String -- }\n"
            "  msg host.log\n"
            ";"
        )


def test_pipeline_rejects_export_quote_input() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "export : run { q:Quote<{ | -- }> -- }\n"
            ";\n"
        )


def test_pipeline_rejects_export_quote_output() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "export : run { -- q:Quote<{ | -- }> }\n"
            "  :[ | -- | ;]\n"
            ";\n"
        )


def test_pipeline_rejects_export_quote_nested_output() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "export : run { xs:List<Quote<{ | -- }>> -- }\n"
            ";\n"
        )


def test_pipeline_rejects_export_custom_type() -> None:
    with pytest.raises(HostABIError, match="ABI-compatible"):
        analyze_program(
            "export : bad { x:Custom -- }\n"
            "  x drop\n"
            ";\n"
        )


def test_pipeline_rejects_export_with_nested_invalid_type() -> None:
    with pytest.raises(HostABIError, match="ABI-compatible"):
        analyze_program(
            "export : bad { x:Result<List<Custom>,String> -- }\n"
            "  x drop\n"
            ";\n"
        )


def test_pipeline_accepts_export_with_nested_valid_abi_types() -> None:
    result = analyze_program(
        "export : ok { xs:List<Result<Int,String>> r:Result<List<Int>,MapError> -- }\n"
        "  xs drop\n"
        "  r drop\n"
        ";\n"
    )

    assert isinstance(result, CheckedProgram)


def test_pipeline_accepts_local_quote_usage() -> None:
    result = analyze_program(
        ": local-ok { -- q:Quote<{ | -- }> }\n"
        "  :[ | -- | ;]\n"
        ";"
    )

    assert isinstance(result, CheckedProgram)


def test_pipeline_rejects_host_call_with_wrong_input_type() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

    with pytest.raises(CheckerError):
        analyze_program(
            "export : send { n:Int -- }\n"
            "  n host.log\n"
            ";",
            host_contract=host_contract,
        )


def test_pipeline_rejects_direct_optional_host_word_call() -> None:
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words(
        [HostWord(name="host.log", signature=host_signature, availability=BindingAvailability.OPTIONAL, effect=HostEffect.PURE)]
    )

    with pytest.raises(ResolutionError, match="optional host word cannot be called directly in v1"):
        analyze_program(
            "export : send { msg:String -- }\n"
            "  msg host.log\n"
            ";",
            host_contract=host_contract,
        )


def test_pipeline_rejects_list_reduce_on_provably_empty_list() -> None:
    with pytest.raises(CheckerError, match="provably empty list"):
        analyze_program(
            "export : bad { -- n:Int }\n"
            "  []:List<Int>\n"
            "  :[ | a:Int b:Int -- c:Int |\n"
            "    a b +\n"
            "  ;]\n"
            "  list.reduce\n"
            ";"
        )


def test_pipeline_accepts_export_with_multiple_host_words() -> None:
    log_signature = signature_from_source(": hostlog { msg:String -- } ;")
    random_signature = signature_from_source(": hostrandom { -- n:Int } ;")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.log", signature=log_signature, effect=HostEffect.PURE),
            HostWord(name="host.random-int", signature=random_signature, effect=HostEffect.PURE),
        ]
    )

    result = analyze_program(
        "export : run { msg:String -- n:Int }\n"
        "  msg host.log\n"
        "  host.random-int\n"
        ";",
        host_contract=host_contract,
    )

    assert "run" in result.export_contract.words
    assert result.export_contract.words["run"].signature is result.symbols.words["run"][0].signature


def test_pipeline_accepts_capturing_quote_for_list_map() -> None:
    result = analyze_program(
        ": main { xs:List<Int> offset:Int -- ys:List<Int> }\n"
        "  xs\n"
        "  offset\n"
        "  :[ captured-offset:Int | x:Int -- y:Int | x captured-offset + ;]\n"
        "  list.map\n"
        ";"
    )

    assert isinstance(result, CheckedProgram)


def test_pipeline_accepts_capturing_quote_for_list_fold() -> None:
    result = analyze_program(
        ": main { xs:List<Int> offset:Int -- n:Int }\n"
        "  xs\n"
        "  0\n"
        "  offset\n"
        "  :[ captured-offset:Int | acc:Int x:Int -- out:Int | acc x + captured-offset + ;]\n"
        "  list.fold\n"
        ";"
    )

    assert isinstance(result, CheckedProgram)


def test_pipeline_accepts_capturing_quote_for_list_reduce() -> None:
    result = analyze_program(
        ": main { xs:List<Int> offset:Int -- n:Int }\n"
        "  xs\n"
        "  offset\n"
        "  :[ captured-offset:Int | a:Int b:Int -- c:Int | a b + captured-offset + ;]\n"
        "  list.reduce\n"
        ";"
    )

    assert isinstance(result, CheckedProgram)


def test_pipeline_accepts_collection_core_step2_builtins() -> None:
    result = analyze_program(
        ": step2 { -- n:Int }\n"
        "  [1, 2] list.reverse list.first drop\n"
        "  map.empty:Map<String,Int> \"a\" 1 map.set map.keys drop\n"
        "  map.empty:Map<String,Int> map.is-empty drop\n"
        "  0\n"
        ";"
    )

    assert isinstance(result, CheckedProgram)


def test_pipeline_accepts_propagate_with_matching_result_error_type() -> None:
    result = analyze_program(
        "export : ok { -- r:Result<Int,MapError> }\n"
        "  map.empty:Map<String,Int>\n"
        '  "k"\n'
        "  map.get\n"
        "  ?\n"
        "  1 +\n"
        "  Ok!\n"
        ";"
    )

    assert isinstance(result, CheckedProgram)


def test_pipeline_rejects_propagate_with_mismatched_error_type() -> None:
    with pytest.raises(CheckerError):
        analyze_program(
            "export : bad { -- r:Result<Int,MapError> }\n"
            "  []:List<Int>\n"
            "  0\n"
            "  list.get\n"
            "  ?\n"
            "  Ok!\n"
            ";"
        )
