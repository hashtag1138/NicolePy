from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.ast_nodes import Visibility
from nicole.errors import DiagnosticPhase
from nicole.host_abi import (
    HostABIError,
    HostEffect,
    HostOpaqueType,
    HostWord,
    collect_exports,
    host_contract_from_words,
)
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.parser import ParseError
from nicole.pipeline import analyze_program
from nicole.symbols import SymbolError, SymbolTable, WordSymbol
from nicole.tokens import SourceSpan


def _signature_from_source(source: str):
    return Parser(lex(source)).parse().words[0].signature


def _export_symbols_for_signature(signature):
    symbols = SymbolTable()
    symbols.add(
        WordSymbol(
            name="run",
            signature=signature,
            visibility=Visibility.EXPORT,
            span=SourceSpan(line=1, column=1, offset=0),
            module="app",
        )
    )
    return symbols


def test_module_local_export_publishes_canonical_name() -> None:
    checked = analyze_program(
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    42\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )

    assert "@app.run" in checked.export_contract.words
    export_word = checked.export_contract.words["@app.run"]
    assert export_word.export_name == "@app.run"
    assert export_word.internal_name == "@app.run"


def test_export_contract_preserves_leading_at_sign() -> None:
    checked = analyze_program(
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    1\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )

    assert "@app.run" in checked.export_contract.words
    assert "app.run" not in checked.export_contract.words


def test_import_alias_does_not_change_canonical_export_name() -> None:
    checked = analyze_program(
        "module @core\n"
        "  : run { -- n:Int }\n"
        "    7\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
        "module @app\n"
        "  import @core as c\n"
        "  : use { -- n:Int }\n"
        "    c.run\n"
        "  ;\n"
        "end-module\n"
    )

    assert set(checked.export_contract.words.keys()) == {"@core.run"}


def test_duplicate_canonical_export_is_rejected() -> None:
    with pytest.raises(SymbolError, match="duplicate export declaration"):
        analyze_program(
            "module @app\n"
            "  : run { -- n:Int }\n"
            "    1\n"
            "  ;\n"
            "  export : run\n"
            "  export : run\n"
            "end-module\n"
        )


def test_export_target_must_exist() -> None:
    with pytest.raises(SymbolError, match="export target does not exist"):
        analyze_program(
            "module @app\n"
            "  export : missing\n"
            "end-module\n"
        )


def test_export_target_must_be_same_module_module_level_word() -> None:
    with pytest.raises(SymbolError, match="export target does not exist"):
        analyze_program(
            "module @lib\n"
            "  : run { -- n:Int }\n"
            "    1\n"
            "  ;\n"
            "end-module\n"
            "module @app\n"
            "  import @lib.run as run\n"
            "  export : run\n"
            "end-module\n"
        )


def test_export_target_cannot_be_subword() -> None:
    with pytest.raises(SymbolError, match="module-level"):
        analyze_program(
            "module @app\n"
            "  : parent { -- }\n"
            "    : child { -- }\n"
            "    ;\n"
            "  ;\n"
            "  export : child\n"
            "end-module\n"
        )


def test_legacy_flat_export_syntax_is_not_public_behavior() -> None:
    with pytest.raises(ParseError, match="export declaration is only allowed inside module"):
        analyze_program(
            "export : app.run { -- n:Int }\n"
            "  42\n"
            ";"
        )


def test_exported_word_still_uses_abi_type_validation() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "module @app\n"
            "  : run { -- q:Quote<{ | -- }> }\n"
            "    :[ | -- | ;]\n"
            "  ;\n"
            "  export : run\n"
            "end-module\n"
        )


def test_host_contract_accepts_declared_host_io_file_handle() -> None:
    contract = host_contract_from_words([], opaque_types=[HostOpaqueType(name="host.io.FileHandle")])
    assert "host.io.FileHandle" in contract.opaque_types


def test_host_contract_accepts_declared_host_net_tcp_socket() -> None:
    contract = host_contract_from_words([], opaque_types=[HostOpaqueType(name="host.net.TcpSocket")])
    assert "host.net.TcpSocket" in contract.opaque_types


@pytest.mark.parametrize("name", ["FileHandle", "opaque.FileHandle", "extern.FileHandle", "foo.bar", "@host.io.FileHandle"])
def test_host_contract_rejects_non_canonical_opaque_type_name(name: str) -> None:
    with pytest.raises(HostABIError, match="host opaque type name must be canonical host\\.\\*"):
        host_contract_from_words([], opaque_types=[HostOpaqueType(name=name)])


def test_host_contract_still_rejects_source_canonical_host_word_name() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(HostABIError, match="host word name must start with 'host.'"):
        host_contract_from_words([HostWord(name="@host.console.log", signature=signature, effect=HostEffect.PURE)])


def test_host_contract_still_rejects_source_canonical_host_word_name_short_path() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(HostABIError, match="host word name must start with 'host.'"):
        host_contract_from_words([HostWord(name="@host.foo", signature=signature, effect=HostEffect.PURE)])


def test_host_contract_rejects_duplicate_opaque_type_declarations() -> None:
    with pytest.raises(HostABIError, match="duplicate host opaque type: host.io.FileHandle"):
        host_contract_from_words(
            [],
            opaque_types=[
                HostOpaqueType(name="host.io.FileHandle"),
                HostOpaqueType(name="host.io.FileHandle"),
            ],
        )


def test_host_contract_has_no_opaque_type_aliasing_mechanism() -> None:
    contract = host_contract_from_words(
        [],
        opaque_types=[HostOpaqueType(name="host.io.FileHandle")],
    )
    assert "FileHandle" not in contract.opaque_types
    assert "host.io.FH" not in contract.opaque_types


def test_host_word_contract_behavior_remains_unchanged_with_opaque_registry() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { msg:String -- }\n"
        "  ;\n"
        "end-module\n"
    )
    contract = host_contract_from_words(
        [HostWord(name="host.log", signature=signature, effect=HostEffect.PURE)],
        opaque_types=[HostOpaqueType(name="host.io.FileHandle")],
    )
    assert "host.log" in contract.words


def test_host_word_signature_accepts_declared_host_opaque_type() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { -- fh:host.io.FileHandle }\n"
        "  ;\n"
        "end-module\n"
    )
    contract = host_contract_from_words(
        [HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)],
        opaque_types=[HostOpaqueType(name="host.io.FileHandle")],
    )
    assert "host.open" in contract.words


def test_host_word_signature_rejects_undeclared_host_opaque_type() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { -- fh:host.io.FileHandle }\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(HostABIError, match="undeclared host opaque type in ABI signature"):
        host_contract_from_words([HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)])


@pytest.mark.parametrize("key_type", ["String", "Int", "Bool"])
def test_host_word_signature_accepts_map_value_declared_host_opaque_type(key_type: str) -> None:
    signature = _signature_from_source(
        "module @sig\n"
        f"  : hostsig {{ -- m:Map<{key_type},host.io.FileHandle> }}\n"
        "  ;\n"
        "end-module\n"
    )
    contract = host_contract_from_words(
        [HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)],
        opaque_types=[HostOpaqueType(name="host.io.FileHandle")],
    )
    assert "host.open" in contract.words


def test_host_word_signature_rejects_map_key_host_opaque_type_even_if_declared() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { -- m:Map<host.io.FileHandle,String> }\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(HostABIError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        host_contract_from_words(
            [HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)],
            opaque_types=[HostOpaqueType(name="host.io.FileHandle")],
        )


def test_host_word_signature_rejects_dirty_quote_unchanged() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { -- q:DirtyQuote<{ | -- }> }\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)])


def test_host_word_signature_rejects_unknown_nominal_type_foo() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { -- out:Foo }\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(HostABIError, match="type is not ABI-compatible in v1: Foo"):
        host_contract_from_words([HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)])


def test_export_signature_accepts_declared_host_opaque_type() -> None:
    signature = _signature_from_source(
        "module @app\n"
        "  : run { -- fh:host.io.FileHandle }\n"
        "  ;\n"
        "end-module\n"
    )
    symbols = _export_symbols_for_signature(signature)
    contract = host_contract_from_words([], opaque_types=[HostOpaqueType(name="host.io.FileHandle")])
    exports = collect_exports(symbols, host_contract=contract)
    assert "@app.run" in exports.words


def test_export_signature_rejects_undeclared_host_opaque_type() -> None:
    signature = _signature_from_source(
        "module @app\n"
        "  : run { -- fh:host.io.FileHandle }\n"
        "  ;\n"
        "end-module\n"
    )
    symbols = _export_symbols_for_signature(signature)
    with pytest.raises(HostABIError, match="undeclared host opaque type in ABI signature"):
        collect_exports(symbols)


@pytest.mark.parametrize("key_type", ["String", "Int", "Bool"])
def test_export_signature_accepts_map_value_declared_host_opaque_type(key_type: str) -> None:
    signature = _signature_from_source(
        "module @app\n"
        f"  : run {{ -- m:Map<{key_type},host.io.FileHandle> }}\n"
        "  ;\n"
        "end-module\n"
    )
    symbols = _export_symbols_for_signature(signature)
    contract = host_contract_from_words([], opaque_types=[HostOpaqueType(name="host.io.FileHandle")])
    exports = collect_exports(symbols, host_contract=contract)
    assert "@app.run" in exports.words


def test_export_signature_rejects_map_key_host_opaque_type_even_if_declared() -> None:
    signature = _signature_from_source(
        "module @app\n"
        "  : run { -- m:Map<host.io.FileHandle,String> }\n"
        "  ;\n"
        "end-module\n"
    )
    symbols = _export_symbols_for_signature(signature)
    contract = host_contract_from_words([], opaque_types=[HostOpaqueType(name="host.io.FileHandle")])
    with pytest.raises(HostABIError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        collect_exports(symbols, host_contract=contract)


def test_export_signature_rejects_quote_unchanged() -> None:
    signature = _signature_from_source(
        "module @app\n"
        "  : run { -- q:Quote<{ | -- }> }\n"
        "  ;\n"
        "end-module\n"
    )
    symbols = _export_symbols_for_signature(signature)
    contract = host_contract_from_words([], opaque_types=[HostOpaqueType(name="host.io.FileHandle")])
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        collect_exports(symbols, host_contract=contract)


def test_export_signature_rejects_dirty_quote_unchanged() -> None:
    signature = _signature_from_source(
        "module @app\n"
        "  : run { -- q:DirtyQuote<{ | -- }> }\n"
        "  ;\n"
        "end-module\n"
    )
    symbols = _export_symbols_for_signature(signature)
    contract = host_contract_from_words([], opaque_types=[HostOpaqueType(name="host.io.FileHandle")])
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        collect_exports(symbols, host_contract=contract)


def test_host_and_export_abi_behavior_is_consistent_for_declared_and_undeclared() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { -- fh:host.io.FileHandle }\n"
        "  ;\n"
        "end-module\n"
    )

    declared_contract = host_contract_from_words([], opaque_types=[HostOpaqueType(name="host.io.FileHandle")])
    host_contract_from_words(
        [HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)],
        opaque_types=[HostOpaqueType(name="host.io.FileHandle")],
    )
    exports = collect_exports(_export_symbols_for_signature(signature), host_contract=declared_contract)
    assert "@app.run" in exports.words

    with pytest.raises(HostABIError, match="undeclared host opaque type in ABI signature"):
        host_contract_from_words([HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)])
    with pytest.raises(HostABIError, match="undeclared host opaque type in ABI signature"):
        collect_exports(_export_symbols_for_signature(signature))


def test_host_abi_error_without_nicole_source_has_no_span() -> None:
    with pytest.raises(HostABIError) as exc_info:
        host_contract_from_words(
            [],
            opaque_types=[
                HostOpaqueType(name="host.io.FileHandle"),
                HostOpaqueType(name="host.io.FileHandle"),
            ],
        )

    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.ABI
    assert error.diagnostic.code == "ABI_DUPLICATE_HOST_OPAQUE_TYPE"
    assert error.diagnostic.span is None


def test_host_abi_error_with_nicole_source_uses_real_span() -> None:
    signature = _signature_from_source(
        "module @sig\n"
        "  : hostsig { -- out:Foo }\n"
        "  ;\n"
        "end-module\n"
    )
    offending_span = signature.outputs[0].type_node.span
    with pytest.raises(HostABIError) as exc_info:
        host_contract_from_words([HostWord(name="host.open", signature=signature, effect=HostEffect.PURE)])

    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.ABI
    assert error.diagnostic.code == "ABI_INVALID_HOST_SIGNATURE"
    assert error.diagnostic.span == offending_span
