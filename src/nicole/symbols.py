from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .ast_nodes import SignatureNode, Visibility
from .tokens import SourceSpan


class SymbolSource(Enum):
    USER = auto()
    BUILTIN = auto()


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
    owner: str | None = None
    source: SymbolSource = SymbolSource.USER
    quote_callable_only: bool = False

    @property
    def qualified_name(self) -> str:
        return _qualified_name(self.owner, self.name)


@dataclass
class SymbolTable:
    words: dict[str, list[WordSymbol]] = field(default_factory=dict)

    def add(self, symbol: WordSymbol) -> None:
        for existing in self.words.get(symbol.name, []):
            if existing.owner == symbol.owner:
                raise SymbolError(
                    message=f"duplicate visible name: {symbol.name}",
                    line=symbol.span.line,
                    column=symbol.span.column,
                )
            # v1 has a single compilation unit visible-name space for words:
            # top-level words and subwords may not share the same name.
            if existing.owner is None or symbol.owner is None:
                raise SymbolError(
                    message=f"duplicate visible name: {symbol.name}",
                    line=symbol.span.line,
                    column=symbol.span.column,
                )
        self.words.setdefault(symbol.name, []).append(symbol)


def _qualified_name(owner: str | None, name: str) -> str:
    if owner is None:
        return name
    return f"{owner}.{name}"
