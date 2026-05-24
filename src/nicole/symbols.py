from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .ast_nodes import SignatureNode, Visibility
from .errors import DiagnosticError, DiagnosticPhase
from .tokens import SourceSpan


class SymbolSource(Enum):
    USER = auto()
    BUILTIN = auto()


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
    quote_callable_only: bool = False

    @property
    def qualified_name(self) -> str:
        return _qualified_name(self.owner, self.name)


@dataclass(frozen=True, slots=True)
class ImportMetadata:
    target: str
    alias: str | None
    span: SourceSpan


@dataclass
class SymbolTable:
    words: dict[str, list[WordSymbol]] = field(default_factory=dict)
    modules: dict[str, SourceSpan] = field(default_factory=dict)
    imports: list[ImportMetadata] = field(default_factory=list)
    aliases: dict[str, ImportMetadata] = field(default_factory=dict)

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

    def add_import(self, target: str, alias: str | None, span: SourceSpan) -> None:
        metadata = ImportMetadata(target=target, alias=alias, span=span)
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
        if alias in self.aliases:
            raise SymbolError(
                message=f"duplicate import alias: {alias}",
                line=span.line,
                column=span.column,
                span=span,
                code="SYMBOLS_DUPLICATE_IMPORT_ALIAS",
            )
        self.aliases[alias] = metadata

    def allows_qualified_reference(self, qualified_reference: str) -> bool:
        normalized = qualified_reference[1:] if qualified_reference.startswith("@") else qualified_reference
        return any(
            _import_target_matches_reference(
                metadata.target,
                normalized,
                known_modules=self.modules,
            )
            for metadata in self.imports
        )

    def alias_target(self, alias: str) -> str | None:
        metadata = self.aliases.get(alias)
        if metadata is None:
            return None
        return metadata.target

    def resolve_alias_reference(self, alias: str, suffix: str | None) -> str | None:
        target = self.alias_target(alias)
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
