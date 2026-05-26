from __future__ import annotations

from dataclasses import dataclass, replace

from .ast_nodes import (
    ExportDeclaration,
    HostOpaqueDeclaration,
    HostRequireDeclaration,
    ImportAliasKind,
    ImportDeclaration,
    ModuleDeclaration,
    ParameterNode,
    ProgramNode,
    QuoteTypeNode,
    SignatureNode,
    TypeNode,
    Visibility,
    WordDefNode,
)
from .symbols import (
    SourceHostCapabilitySymbol,
    SourceHostContract,
    SourceHostOpaqueTypeSymbol,
    SymbolError,
    SymbolTable,
    WordSymbol,
)

__all__ = ["CollectedSemanticModel", "collect_semantic_model", "collect_signatures"]


@dataclass(frozen=True, slots=True)
class CollectedSemanticModel:
    symbols: SymbolTable
    source_host_contract: SourceHostContract


def collect_signatures(program: ProgramNode) -> SymbolTable:
    return collect_semantic_model(program).symbols


def collect_semantic_model(program: ProgramNode) -> CollectedSemanticModel:
    table = SymbolTable()
    source_host_contract = SourceHostContract()
    for declaration in program.declarations:
        if not isinstance(declaration, ModuleDeclaration):
            continue
        if declaration.is_host_module:
            _collect_host_module(declaration, source_host_contract)
            continue
        _collect_module(declaration, table)
    return CollectedSemanticModel(symbols=table, source_host_contract=source_host_contract)


def _collect_module(declaration: ModuleDeclaration, table: SymbolTable) -> None:
    module_name = _module_key(declaration.name.parts)
    table.add_module(module_name, declaration.span)

    export_declarations: list[ExportDeclaration] = []
    for item in declaration.items:
        if isinstance(item, ImportDeclaration):
            _collect_import(item, table, owner_module=module_name)
            continue
        if isinstance(item, WordDefNode):
            _collect_word(item, table, module=module_name, owner=None)
            continue
        if isinstance(item, ExportDeclaration):
            export_declarations.append(item)

    _apply_module_exports(export_declarations, table, module_name=module_name)


def _collect_host_module(declaration: ModuleDeclaration, source_host_contract: SourceHostContract) -> None:
    for item in declaration.items:
        if isinstance(item, HostRequireDeclaration):
            _collect_host_capability(item, source_host_contract)
        elif isinstance(item, HostOpaqueDeclaration):
            _collect_host_opaque(item, source_host_contract)


def _collect_host_capability(
    declaration: HostRequireDeclaration,
    source_host_contract: SourceHostContract,
) -> None:
    canonical_name = _canonical_host_name(declaration.path.parts)
    existing = source_host_contract.capabilities.get(canonical_name)
    if existing is not None:
        if _same_signature(existing.signature, declaration.signature) and existing.effect == declaration.effect:
            return
        raise SymbolError(
            message=f"conflicting host capability declaration: {canonical_name}",
            line=declaration.span.line,
            column=declaration.span.column,
            span=declaration.span,
            code="SYMBOLS_HOST_CAPABILITY_CONFLICT",
        )

    if canonical_name in source_host_contract.opaque_types:
        raise SymbolError(
            message=f"host symbol category conflict: {canonical_name}",
            line=declaration.span.line,
            column=declaration.span.column,
            span=declaration.span,
            code="SYMBOLS_HOST_CATEGORY_CONFLICT",
        )

    source_host_contract.capabilities[canonical_name] = SourceHostCapabilitySymbol(
        canonical_name=canonical_name,
        path=declaration.path.parts,
        signature=declaration.signature,
        effect=declaration.effect,
        span=declaration.span,
    )


def _collect_host_opaque(
    declaration: HostOpaqueDeclaration,
    source_host_contract: SourceHostContract,
) -> None:
    canonical_name = _canonical_host_name(declaration.path.parts)
    if canonical_name in source_host_contract.capabilities:
        raise SymbolError(
            message=f"host symbol category conflict: {canonical_name}",
            line=declaration.span.line,
            column=declaration.span.column,
            span=declaration.span,
            code="SYMBOLS_HOST_CATEGORY_CONFLICT",
        )
    if canonical_name in source_host_contract.opaque_types:
        return

    source_host_contract.opaque_types[canonical_name] = SourceHostOpaqueTypeSymbol(
        canonical_name=canonical_name,
        path=declaration.path.parts,
        span=declaration.span,
    )


def _collect_import(declaration: ImportDeclaration, table: SymbolTable, *, owner_module: str) -> None:
    target = _module_key(declaration.target.parts)
    if not declaration.is_grouped:
        table.add_import(owner_module=owner_module, target=target, alias=declaration.alias, span=declaration.span)
        return

    for member in declaration.grouped_members:
        member_target = f"{target}.{member}"
        if declaration.alias_kind is ImportAliasKind.STAR:
            member_alias = member
        elif declaration.alias_kind is ImportAliasKind.PREFIX:
            if declaration.alias is None:
                raise SymbolError(
                    message="grouped import requires an alias",
                    line=declaration.span.line,
                    column=declaration.span.column,
                    span=declaration.span,
                    code="SYMBOLS_GROUPED_IMPORT_ALIAS_REQUIRED",
                )
            member_alias = f"{declaration.alias}.{member}"
        else:
            raise SymbolError(
                message="unsupported grouped import alias kind",
                line=declaration.span.line,
                column=declaration.span.column,
                span=declaration.span,
                code="SYMBOLS_GROUPED_IMPORT_ALIAS_KIND_UNSUPPORTED",
            )

        table.add_import(
            owner_module=owner_module,
            target=member_target,
            alias=member_alias,
            span=declaration.span,
            is_grouped_expansion=True,
            group_parent_target=target,
            group_member=member,
        )


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
                span=export.span,
                code="SYMBOLS_EXPORT_TARGET_NOT_FOUND",
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
                span=export.span,
                code="SYMBOLS_EXPORT_TARGET_NOT_MODULE_LEVEL",
            )

        target = module_level_symbols[0]
        canonical_name = f"@{module_name}.{target.name}"
        if canonical_name in seen_canonical:
            raise SymbolError(
                message=f"duplicate export declaration: {canonical_name}",
                line=export.span.line,
                column=export.span.column,
                span=export.span,
                code="SYMBOLS_DUPLICATE_EXPORT",
            )
        seen_canonical.add(canonical_name)

        symbols_for_name = table.words[target.name]
        for index, symbol in enumerate(symbols_for_name):
            if symbol is target:
                symbols_for_name[index] = replace(symbol, visibility=Visibility.EXPORT)
                break


def _module_key(parts: tuple[str, ...]) -> str:
    return ".".join(parts)


def _canonical_host_name(parts: tuple[str, ...]) -> str:
    return f"@host.{'.'.join(parts)}"


def _same_signature(left: SignatureNode, right: SignatureNode) -> bool:
    return (
        _same_parameters(left.inputs, right.inputs)
        and _same_parameters(left.outputs, right.outputs)
    )


def _same_parameters(left: tuple[ParameterNode, ...], right: tuple[ParameterNode, ...]) -> bool:
    if len(left) != len(right):
        return False
    return all(
        _same_parameter(left_parameter, right_parameter)
        for left_parameter, right_parameter in zip(left, right, strict=True)
    )


def _same_parameter(left: ParameterNode, right: ParameterNode) -> bool:
    return left.name == right.name and _same_type_node(left.type_node, right.type_node)


def _same_type_node(left: TypeNode | QuoteTypeNode, right: TypeNode | QuoteTypeNode) -> bool:
    if isinstance(left, TypeNode) and isinstance(right, TypeNode):
        if left.name != right.name or len(left.args) != len(right.args):
            return False
        return all(
            _same_type_node(left_argument, right_argument)
            for left_argument, right_argument in zip(left.args, right.args, strict=True)
        )
    if isinstance(left, QuoteTypeNode) and isinstance(right, QuoteTypeNode):
        return (
            left.effect_kind == right.effect_kind
            and _same_parameters(left.captures, right.captures)
            and _same_parameters(left.inputs, right.inputs)
            and _same_parameters(left.outputs, right.outputs)
        )
    return False
