from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .ast_nodes import SignatureNode, Visibility
from .tokens import SourceSpan


class SymbolSource(Enum):
    USER = auto()
    BUILTIN = auto()


_RESERVED_ROOTS = {"host", "list", "map", "result"}


@dataclass(slots=True)
class SymbolError(Exception):
    message: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.message} at {self.line}:{self.column}"


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
                )
        self.words.setdefault(symbol.name, []).append(symbol)

    def add_module(self, module_name: str, span: SourceSpan) -> None:
        root = module_name.split(".", 1)[0]
        if root in _RESERVED_ROOTS:
            raise SymbolError(
                message=f"cannot use reserved root as module name: @{module_name}",
                line=span.line,
                column=span.column,
            )
        if module_name in self.modules:
            raise SymbolError(
                message=f"duplicate module declaration: {module_name}",
                line=span.line,
                column=span.column,
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
            )
        if alias in self.aliases:
            raise SymbolError(
                message=f"duplicate import alias: {alias}",
                line=span.line,
                column=span.column,
            )
        self.aliases[alias] = metadata


def _qualified_name(owner: str | None, name: str) -> str:
    if owner is None:
        return name
    return f"{owner}.{name}"
