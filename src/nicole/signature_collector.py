from __future__ import annotations

from .ast_nodes import ProgramNode, WordDefNode
from .symbols import SymbolTable, WordSymbol

__all__ = ["collect_signatures"]


def collect_signatures(program: ProgramNode) -> SymbolTable:
    table = SymbolTable()
    for word in program.words:
        _collect_word(word, table, owner=None)
    return table


def _collect_word(word: WordDefNode, table: SymbolTable, owner: str | None) -> None:
    symbol = WordSymbol(
        name=word.name,
        signature=word.signature,
        visibility=word.visibility,
        span=word.span,
        owner=owner,
    )
    table.add(symbol)

    current_owner = symbol.qualified_name
    for nested in word.nested_words:
        _collect_word(nested, table, owner=current_owner)
