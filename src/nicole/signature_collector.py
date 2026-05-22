from __future__ import annotations

from .ast_nodes import ImportDeclaration, ModuleDeclaration, ProgramNode, WordDefNode
from .symbols import SymbolTable, WordSymbol

__all__ = ["collect_signatures"]


def collect_signatures(program: ProgramNode) -> SymbolTable:
    table = SymbolTable()
    for declaration in program.declarations:
        if isinstance(declaration, ModuleDeclaration):
            _collect_module(declaration, table)
            continue
        if isinstance(declaration, ImportDeclaration):
            _collect_import(declaration, table)
            continue
    return table


def _collect_module(declaration: ModuleDeclaration, table: SymbolTable) -> None:
    module_name = _module_key(declaration.name.parts)
    table.add_module(module_name, declaration.span)

    for item in declaration.items:
        if isinstance(item, WordDefNode):
            _collect_word(item, table, module=module_name, owner=None)


def _collect_import(declaration: ImportDeclaration, table: SymbolTable) -> None:
    target = _module_key(declaration.target.parts)
    table.add_import(target=target, alias=declaration.alias, span=declaration.span)


def _collect_word(word: WordDefNode, table: SymbolTable, *, module: str | None, owner: str | None) -> None:
    symbol = WordSymbol(
        name=word.name,
        signature=word.signature,
        visibility=word.visibility,
        span=word.span,
        declared_dirty=word.is_dirty_annotation,
        module=module,
        owner=owner,
    )
    table.add(symbol)

    current_owner = symbol.qualified_name
    for nested in word.nested_words:
        _collect_word(nested, table, module=module, owner=current_owner)


def _module_key(parts: tuple[str, ...]) -> str:
    return ".".join(parts)
