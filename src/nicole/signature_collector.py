from __future__ import annotations

from dataclasses import replace

from .ast_nodes import ExportDeclaration, ImportDeclaration, ModuleDeclaration, ProgramNode, Visibility, WordDefNode
from .symbols import SymbolError, SymbolTable, WordSymbol

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

    export_declarations: list[ExportDeclaration] = []
    for item in declaration.items:
        if isinstance(item, WordDefNode):
            _collect_word(item, table, module=module_name, owner=None)
            continue
        if isinstance(item, ExportDeclaration):
            export_declarations.append(item)

    _apply_module_exports(export_declarations, table, module_name=module_name)


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


def _apply_module_exports(
    exports: list[ExportDeclaration],
    table: SymbolTable,
    *,
    module_name: str,
) -> None:
    seen_canonical: set[str] = set()

    for export in exports:
        module_symbols = [
            symbol
            for symbol in table.words.get(export.word_name, [])
            if symbol.module == module_name
        ]
        if not module_symbols:
            raise SymbolError(
                message=f"export target does not exist in module @{module_name}: {export.word_name}",
                line=export.span.line,
                column=export.span.column,
            )

        module_level_symbols = [
            symbol
            for symbol in module_symbols
            if symbol.owner is None
        ]
        if not module_level_symbols:
            raise SymbolError(
                message=f"export target must be a module-level word: {export.word_name}",
                line=export.span.line,
                column=export.span.column,
            )

        target = module_level_symbols[0]
        canonical_name = f"@{module_name}.{target.name}"
        if canonical_name in seen_canonical:
            raise SymbolError(
                message=f"duplicate export declaration: {canonical_name}",
                line=export.span.line,
                column=export.span.column,
            )
        seen_canonical.add(canonical_name)

        symbols_for_name = table.words[target.name]
        for index, symbol in enumerate(symbols_for_name):
            if symbol is target:
                symbols_for_name[index] = replace(symbol, visibility=Visibility.EXPORT)
                break


def _module_key(parts: tuple[str, ...]) -> str:
    return ".".join(parts)
