from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import ProgramNode
from .checker import check_program
from .host_abi import ExportContract, HostContract, collect_exports, empty_host_contract
from .lexer import lex, lex_source
from .parser import Parser
from .resolver import resolve
from .source import SourceFile
from .signature_collector import collect_signatures
from .standard_symbols import with_standard_symbols
from .symbols import SymbolTable
from .tokens import Token


@dataclass(frozen=True, slots=True)
class CheckedProgram:
    program: ProgramNode
    symbols: SymbolTable
    host_contract: HostContract
    export_contract: ExportContract


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
    effective_host_contract = host_contract if host_contract is not None else empty_host_contract()
    program = Parser(tokens).parse()
    symbols = collect_signatures(program)
    symbols = with_standard_symbols(symbols)
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
    )
