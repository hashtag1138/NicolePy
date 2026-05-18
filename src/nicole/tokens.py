from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    EOF = auto()

    COLON = auto()
    SEMICOLON = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LPAREN = auto()
    RPAREN = auto()
    BAR = auto()
    COMMA = auto()
    LT = auto()
    GT = auto()

    STACK_ARROW = auto()
    CASE_ARROW = auto()
    QUOTE_START = auto()
    QUOTE_END = auto()

    PUB = auto()
    EXPORT = auto()
    IF = auto()
    ELSE = auto()
    END = auto()
    CASE = auto()
    UNDERSCORE = auto()

    INT_LITERAL = auto()
    FLOAT_LITERAL = auto()
    STRING_LITERAL = auto()
    BOOL_LITERAL = auto()

    IDENTIFIER = auto()
    OPERATOR = auto()


@dataclass(frozen=True, slots=True)
class SourceSpan:
    line: int
    column: int
    offset: int


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    lexeme: str
    span: SourceSpan

    def __str__(self) -> str:
        return (
            f"{self.kind.name}("
            f"{self.lexeme!r}"
            f")@{self.span.line}:{self.span.column}"
        )
