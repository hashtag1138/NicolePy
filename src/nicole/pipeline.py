from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import ProgramNode
from .checker import check_program
from .host_abi import ExportContract, HostContract, HostEffect, HostOpaqueType, HostWord, collect_exports, empty_host_contract, host_contract_from_words
from .lexer import lex, lex_source
from .parser import Parser
from .resolver import resolve
from .source import SourceFile
from .signature_collector import collect_semantic_model
from .standard_symbols import with_standard_symbols
from .symbols import SourceHostContract, SymbolTable
from .tokens import Token


@dataclass(frozen=True, slots=True)
class CheckedProgram:
    program: ProgramNode
    symbols: SymbolTable
    host_contract: HostContract
    export_contract: ExportContract
    source_files: tuple[SourceFile, ...] = ()


def analyze_program(source: str, *, host_contract: HostContract | None = None) -> CheckedProgram:
    return _analyze_tokens(
        lex(source),
        host_contract=host_contract,
    )


def _analyze_source_file(source_file: SourceFile, *, host_contract: HostContract | None = None) -> CheckedProgram:
    return _analyze_tokens(
        lex_source(source_file),
        host_contract=host_contract,
    )


def _analyze_tokens(tokens: list[Token], *, host_contract: HostContract | None = None) -> CheckedProgram:
    program = Parser(tokens).parse()
    return _analyze_program(
        program,
        host_contract=host_contract,
    )


def _analyze_program(program: ProgramNode, *, host_contract: HostContract | None = None) -> CheckedProgram:
    semantic_model = collect_semantic_model(program)
    symbols = semantic_model.symbols
    symbols = with_standard_symbols(symbols)
    source_host_contract = _legacy_host_contract_from_source(semantic_model.source_host_contract)
    if source_host_contract is not None:
        effective_host_contract = source_host_contract
    else:
        effective_host_contract = host_contract if host_contract is not None else empty_host_contract()
    resolved = resolve(program, symbols, host_contract=effective_host_contract)
    checked = check_program(
        resolved,
        symbols,
        declared_opaque_type_names=frozenset(effective_host_contract.opaque_types),
    )
    export_contract = collect_exports(symbols, host_contract=effective_host_contract)
    return CheckedProgram(
        program=checked,
        symbols=symbols,
        host_contract=effective_host_contract,
        export_contract=export_contract,
        source_files=(),
    )


def _legacy_host_contract_from_source(source_host_contract: SourceHostContract) -> HostContract | None:
    if not source_host_contract.has_entries():
        return None
    words = [
        HostWord(
            name=_canonical_to_legacy(canonical_name),
            signature=symbol.signature,
            effect=HostEffect.PURE if symbol.effect.value == "pure" else HostEffect.DIRTY,
        )
        for canonical_name, symbol in source_host_contract.capabilities.items()
    ]
    opaque_types = [
        HostOpaqueType(name=_canonical_to_legacy(canonical_name))
        for canonical_name in source_host_contract.opaque_types
    ]
    return host_contract_from_words(words, opaque_types=opaque_types)


def _canonical_to_legacy(canonical_name: str) -> str:
    if not canonical_name.startswith("@host."):
        raise ValueError(f"expected canonical @host.* name, got: {canonical_name}")
    return f"host.{canonical_name[len('@host.'):]}"
