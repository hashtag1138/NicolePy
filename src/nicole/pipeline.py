from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import ProgramNode
from .checker import check_program
from .host_abi import ExportContract, HostContract, collect_exports, empty_host_contract
from .lexer import lex
from .parser import Parser
from .resolver import resolve
from .signature_collector import collect_signatures
from .standard_symbols import with_standard_symbols
from .symbols import SymbolTable


@dataclass(frozen=True, slots=True)
class CheckedProgram:
    program: ProgramNode
    symbols: SymbolTable
    host_contract: HostContract
    export_contract: ExportContract


def analyze_program(source: str, *, host_contract: HostContract | None = None) -> CheckedProgram:
    effective_host_contract = host_contract if host_contract is not None else empty_host_contract()
    program = Parser(lex(source)).parse()
    symbols = collect_signatures(program)
    symbols = with_standard_symbols(symbols)
    resolved = resolve(program, symbols, host_contract=effective_host_contract)
    checked = check_program(resolved, symbols)
    export_contract = collect_exports(symbols, host_contract=effective_host_contract)
    return CheckedProgram(
        program=checked,
        symbols=symbols,
        host_contract=effective_host_contract,
        export_contract=export_contract,
    )
