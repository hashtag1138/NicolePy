from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.ast_nodes import ParameterNode, SignatureNode, TypeNode, Visibility
from nicole.host_abi import (
    BindingAvailability,
    ExportContract,
    ExportWord,
    HostABIError,
    HostWord,
    collect_exports,
    empty_export_contract,
    empty_host_contract,
    export_contract_from_words,
    host_contract_from_words,
)
from nicole.checker import check_program
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.resolver import resolve
from nicole.signature_collector import collect_signatures
from nicole.symbols import SymbolSource, SymbolTable, WordSymbol
from nicole.standard_symbols import with_standard_symbols
from nicole.tokens import SourceSpan


def make_span() -> SourceSpan:
    return SourceSpan(line=1, column=1, offset=0)


def signature_from_source(source: str) -> SignatureNode:
    return Parser(lex(source)).parse().words[0].signature


def test_host_word_uses_signature_node() -> None:
    signature = SignatureNode(
        span=make_span(),
        inputs=(
            ParameterNode(
                span=make_span(),
                name="x",
                type_node=TypeNode(span=make_span(), name="Int"),
            ),
        ),
        outputs=(
            ParameterNode(
                span=make_span(),
                name="y",
                type_node=TypeNode(span=make_span(), name="Int"),
            ),
        ),
    )

    word = HostWord(name="host.math.inc", signature=signature, availability=BindingAvailability.REQUIRED)

    assert word.signature is signature


def test_export_word_uses_signature_node() -> None:
    signature = SignatureNode(
        span=make_span(),
        inputs=(),
        outputs=(
            ParameterNode(
                span=make_span(),
                name="code",
                type_node=TypeNode(span=make_span(), name="Int"),
            ),
        ),
    )

    word = ExportWord(export_name="app.main", internal_name="main", signature=signature)

    assert word.signature is signature


def test_empty_host_contract_starts_empty() -> None:
    contract = empty_host_contract()

    assert dict(contract.words) == {}


def test_host_contract_rejects_name_without_host_prefix() -> None:
    signature = SignatureNode(span=make_span(), inputs=(), outputs=())

    with pytest.raises(HostABIError, match="host word name must start with 'host.'"):
        host_contract_from_words([HostWord(name="log", signature=signature)])


def test_host_contract_rejects_duplicate_host_names() -> None:
    signature = SignatureNode(span=make_span(), inputs=(), outputs=())

    with pytest.raises(HostABIError, match="duplicate host word"):
        host_contract_from_words(
            [
                HostWord(name="host.log", signature=signature),
                HostWord(name="host.log", signature=signature),
            ]
        )


def test_empty_export_contract_starts_empty() -> None:
    contract = empty_export_contract()

    assert isinstance(contract, ExportContract)
    assert dict(contract.words) == {}


def test_export_contract_from_words_builds_simple_export() -> None:
    signature = signature_from_source(": send { msg:String -- } ;")

    contract = export_contract_from_words(
        [ExportWord(export_name="send", internal_name="send", signature=signature)]
    )

    assert contract.words["send"].signature is signature
    assert contract.words["send"].internal_name == "send"


def test_export_contract_rejects_duplicate_public_name() -> None:
    signature = signature_from_source(": send { msg:String -- } ;")

    with pytest.raises(HostABIError, match="duplicate export word"):
        export_contract_from_words(
            [
                ExportWord(export_name="send", internal_name="a.send", signature=signature),
                ExportWord(export_name="send", internal_name="b.send", signature=signature),
            ]
        )


def test_collect_exports_ignores_pub_only_words() -> None:
    program = Parser(lex("pub : helper { -- } ;")).parse()
    symbols = collect_signatures(program)

    contract = collect_exports(symbols)

    assert dict(contract.words) == {}


def test_collect_exports_builds_export_entry() -> None:
    program = Parser(lex("export : send { msg:String -- } msg host.log ;")).parse()
    symbols = collect_signatures(program)

    contract = collect_exports(symbols)

    assert "send" in contract.words
    assert contract.words["send"].export_name == "send"
    assert contract.words["send"].internal_name == "send"
    assert contract.words["send"].signature is symbols.words["send"][0].signature


def test_collect_exports_rejects_duplicate_abi_name_across_scopes() -> None:
    signature = signature_from_source(": helper { -- } ;")
    table = SymbolTable(
        words={
            "send": [
                WordSymbol(
                    name="send",
                    signature=signature,
                    visibility=Visibility.EXPORT,
                    span=make_span(),
                    owner="a",
                    source=SymbolSource.USER,
                ),
                WordSymbol(
                    name="send",
                    signature=signature,
                    visibility=Visibility.EXPORT,
                    span=make_span(),
                    owner="b",
                    source=SymbolSource.USER,
                ),
            ]
        }
    )

    with pytest.raises(HostABIError, match="duplicate export word"):
        collect_exports(table)


def test_export_contract_integration_with_host_checked_program() -> None:
    program = Parser(
        lex(
            "export : send { msg:String -- }\n"
            "  msg host.log\n"
            ";"
        )
    ).parse()
    symbols = with_standard_symbols(collect_signatures(program))
    host_signature = signature_from_source(": hostsig { msg:String -- } ;")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature)])

    resolved = resolve(program, symbols, host_contract=host_contract)
    check_program(resolved, symbols)
    export_contract = collect_exports(symbols)

    assert "send" in export_contract.words
    assert export_contract.words["send"].signature is symbols.words["send"][0].signature


def test_host_contract_rejects_quote_input_type() -> None:
    signature = signature_from_source(": hostsig { q:Quote<{ | -- }> -- } ;")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.run", signature=signature)])


def test_host_contract_rejects_quote_output_type() -> None:
    signature = signature_from_source(": hostsig { -- q:Quote<{ | -- }> } ;")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.make", signature=signature)])


def test_host_contract_rejects_quote_nested_in_list() -> None:
    signature = signature_from_source(": hostsig { xs:List<Quote<{ | -- }>> -- } ;")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.run", signature=signature)])


def test_host_contract_rejects_quote_nested_in_result() -> None:
    signature = signature_from_source(": hostsig { -- r:Result<List<Quote<{ | -- }>>,MapError> } ;")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.run", signature=signature)])


def test_host_contract_rejects_invalid_map_key_type() -> None:
    signature = signature_from_source(": hostsig { -- m:Map<List<Int>,String> } ;")
    with pytest.raises(HostABIError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        host_contract_from_words([HostWord(name="host.run", signature=signature)])
