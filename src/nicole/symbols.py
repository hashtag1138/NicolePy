from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .ast_nodes import HostAbiEffect, SignatureNode, Visibility
from .errors import DiagnosticError, DiagnosticPhase
from .tokens import SourceSpan


class SymbolSource(Enum):
    USER = auto()
    BUILTIN = auto()


class SymbolCategory(Enum):
    USER_WORD = auto()
    BUILTIN_WORD = auto()
    HOST_CAPABILITY = auto()
    HOST_OPAQUE_TYPE = auto()


_RESERVED_ROOTS = {"host", "list", "map", "result"}


class SymbolError(DiagnosticError):
    phase = DiagnosticPhase.SYMBOLS
    default_code = "SYMBOLS_ERROR"


@dataclass(frozen=True, slots=True)
class WordSymbol:
    name: str
    signature: SignatureNode
    visibility: Visibility
    span: SourceSpan
    declared_dirty: bool = False
    module: str | None = None
    owner: str | None = None
    source: SymbolSource = SymbolSource.USER
    category: SymbolCategory = SymbolCategory.USER_WORD
    quote_callable_only: bool = False

    def __post_init__(self) -> None:
        if self.source is SymbolSource.BUILTIN and self.category is SymbolCategory.USER_WORD:
            object.__setattr__(self, "category", SymbolCategory.BUILTIN_WORD)

    @property
    def qualified_name(self) -> str:
        return _qualified_name(self.owner, self.name)


@dataclass(frozen=True, slots=True)
class ImportMetadata:
    owner_module: str
    target: str
    alias: str | None
    span: SourceSpan
    is_grouped_expansion: bool = False
    group_parent_target: str | None = None
    group_member: str | None = None


@dataclass(frozen=True, slots=True)
class SourceHostCapabilitySymbol:
    canonical_name: str
    path: tuple[str, ...]
    signature: SignatureNode
    effect: HostAbiEffect
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class SourceHostOpaqueTypeSymbol:
    canonical_name: str
    path: tuple[str, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class SourceHostContract:
    capabilities: dict[str, SourceHostCapabilitySymbol] = field(default_factory=dict)
    opaque_types: dict[str, SourceHostOpaqueTypeSymbol] = field(default_factory=dict)

    def has_entries(self) -> bool:
        return bool(self.capabilities or self.opaque_types)


@dataclass
class SymbolTable:
    words: dict[str, list[WordSymbol]] = field(default_factory=dict)
    modules: dict[str, SourceSpan] = field(default_factory=dict)
    imports: list[ImportMetadata] = field(default_factory=list)
    aliases: dict[tuple[str, str], ImportMetadata] = field(default_factory=dict)

    def add(self, symbol: WordSymbol) -> None:
        for existing in self.words.get(symbol.name, []):
            if existing.module == symbol.module and existing.owner == symbol.owner:
                raise SymbolError(
                    message=f"duplicate visible name: {symbol.name}",
                    line=symbol.span.line,
                    column=symbol.span.column,
                    span=symbol.span,
                    code="SYMBOLS_DUPLICATE_VISIBLE_NAME",
                )
        self.words.setdefault(symbol.name, []).append(symbol)

    def add_module(self, module_name: str, span: SourceSpan) -> None:
        root = module_name.split(".", 1)[0]
        if root in _RESERVED_ROOTS:
            raise SymbolError(
                message=f"cannot use reserved root as module name: @{module_name}",
                line=span.line,
                column=span.column,
                span=span,
                code="SYMBOLS_RESERVED_MODULE_ROOT",
            )
        if module_name in self.modules:
            raise SymbolError(
                message=f"duplicate module declaration: {module_name}",
                line=span.line,
                column=span.column,
                span=span,
                code="SYMBOLS_DUPLICATE_MODULE_DECLARATION",
            )
        self.modules[module_name] = span

    def add_import(
        self,
        owner_module: str,
        target: str,
        alias: str | None,
        span: SourceSpan,
        *,
        is_grouped_expansion: bool = False,
        group_parent_target: str | None = None,
        group_member: str | None = None,
    ) -> None:
        metadata = ImportMetadata(
            owner_module=owner_module,
            target=target,
            alias=alias,
            span=span,
            is_grouped_expansion=is_grouped_expansion,
            group_parent_target=group_parent_target,
            group_member=group_member,
        )
        self.imports.append(metadata)

        if alias is None:
            return
        if alias in _RESERVED_ROOTS:
            raise SymbolError(
                message=f"cannot use reserved root as import alias: {alias}",
                line=span.line,
                column=span.column,
                span=span,
                code="SYMBOLS_RESERVED_IMPORT_ALIAS",
            )
        alias_key = (owner_module, alias)
        if alias_key in self.aliases:
            raise SymbolError(
                message=f"duplicate import alias: {alias}",
                line=span.line,
                column=span.column,
                span=span,
                code="SYMBOLS_DUPLICATE_IMPORT_ALIAS",
            )
        self.aliases[alias_key] = metadata

    def allows_qualified_reference(self, owner_module: str, qualified_reference: str) -> bool:
        normalized = qualified_reference[1:] if qualified_reference.startswith("@") else qualified_reference
        return any(
            _import_target_matches_reference(
                metadata.target,
                normalized,
                known_modules=self.modules,
            )
            for metadata in self.imports
            if metadata.owner_module == owner_module
        )

    def alias_target(self, owner_module: str, alias: str) -> str | None:
        metadata = self.aliases.get((owner_module, alias))
        if metadata is None:
            return None
        return metadata.target

    def resolve_alias_reference(self, owner_module: str, alias: str, suffix: str | None) -> str | None:
        if suffix is not None:
            exact_target = self.alias_target(owner_module, f"{alias}.{suffix}")
            if exact_target is not None:
                return exact_target

        target = self.alias_target(owner_module, alias)
        if target is None:
            return None

        is_module_target = target in self.modules

        # import @module.word as alias => alias resolves directly to that imported word.
        if not is_module_target:
            if suffix is None:
                return target
            return None

        # import @module as alias => alias.word resolves to @module.word
        if suffix is None:
            return None
        return f"{target}.{suffix}"


def _qualified_name(owner: str | None, name: str) -> str:
    if owner is None:
        return name
    return f"{owner}.{name}"


def _import_target_matches_reference(
    target: str,
    qualified_reference: str,
    *,
    known_modules: dict[str, SourceSpan],
) -> bool:
    is_module_target = target in known_modules
    if not is_module_target:
        return target == qualified_reference
    return qualified_reference.startswith(f"{target}.")
