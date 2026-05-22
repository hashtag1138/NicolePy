from __future__ import annotations

from dataclasses import dataclass

from .tokens import SourceSpan, Token, TokenKind

__all__ = ["LexError", "Lexer", "lex"]


@dataclass(slots=True)
class LexError(Exception):
    message: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.message} at {self.line}:{self.column}"


class Lexer:
    """Strict lexer for Nicole source text."""

    def __init__(self) -> None:
        self.source = ""
        self._source_len = 0
        self._index = 0
        self._line = 1
        self._column = 1
        self._tokens: list[Token] = []

    def tokenize(self, source: str) -> list[Token]:
        self.source = source
        self._source_len = len(source)
        self._index = 0
        self._line = 1
        self._column = 1
        self._tokens: list[Token] = []

        while not self._at_end():
            ch = self._peek()

            if ch in " \t\f\v":
                self._advance()
                continue

            if ch in "\r\n":
                self._consume_newline()
                continue

            if ch == "#":
                self._consume_comment()
                continue

            if self._match(":["):
                self._emit(TokenKind.QUOTE_START, ":[", 2)
                continue

            if self._match(";]"):
                self._emit(TokenKind.QUOTE_END, ";]", 2)
                continue

            if self._match("--"):
                self._emit(TokenKind.STACK_ARROW, "--", 2)
                continue

            if self._match("=>"):
                self._emit(TokenKind.CASE_ARROW, "=>", 2)
                continue

            if self._match("Ok!"):
                self._emit(TokenKind.RESULT_OK, "Ok!", 3)
                continue

            if self._match("Err!"):
                self._emit(TokenKind.RESULT_ERR, "Err!", 4)
                continue

            if ch == '"':
                self._lex_string()
                continue

            if ch.isdigit():
                self._lex_number()
                continue

            if ch == "?":
                self._emit(TokenKind.PROPAGATE, "?", 1)
                continue

            if ch == "@":
                self._lex_qualified_module_name()
                continue

            if _is_identifier_start(ch):
                self._lex_identifier_or_keyword()
                continue

            if ch == ":":
                self._emit(TokenKind.COLON, ":", 1)
                continue

            if ch == "{":
                self._emit(TokenKind.LBRACE, "{", 1)
                continue

            if ch == "}":
                self._emit(TokenKind.RBRACE, "}", 1)
                continue

            if ch == "[":
                self._emit(TokenKind.LBRACKET, "[", 1)
                continue

            if ch == "]":
                self._emit(TokenKind.RBRACKET, "]", 1)
                continue

            if ch == "(":
                self._emit(TokenKind.LPAREN, "(", 1)
                continue

            if ch == ")":
                self._emit(TokenKind.RPAREN, ")", 1)
                continue

            if ch == "|":
                self._emit(TokenKind.BAR, "|", 1)
                continue

            if ch == ",":
                self._emit(TokenKind.COMMA, ",", 1)
                continue

            if ch == ";":
                self._emit(TokenKind.SEMICOLON, ";", 1)
                continue

            if ch == "<":
                if self._match("<="):
                    self._emit(TokenKind.OPERATOR, "<=", 2)
                else:
                    self._emit(TokenKind.LT, "<", 1)
                continue

            if ch == ">":
                if self._match(">="):
                    self._emit(TokenKind.OPERATOR, ">=", 2)
                else:
                    self._emit(TokenKind.GT, ">", 1)
                continue

            if self._match("+."):
                self._emit(TokenKind.OPERATOR, "+.", 2)
                continue

            if self._match("-."):
                self._emit(TokenKind.OPERATOR, "-.", 2)
                continue

            if self._match("*."):
                self._emit(TokenKind.OPERATOR, "*.", 2)
                continue

            if self._match("/."):
                self._emit(TokenKind.OPERATOR, "/.", 2)
                continue

            if ch in "+-*=":
                self._emit(TokenKind.OPERATOR, ch, 1)
                continue

            if ch == "!":
                if self._match("!="):
                    self._emit(TokenKind.OPERATOR, "!=", 2)
                    continue
                self._raise_error("invalid character")

            self._raise_error("invalid character")

        self._tokens.append(
            Token(
                kind=TokenKind.EOF,
                lexeme="",
                span=SourceSpan(self._line, self._column, self._index),
            )
        )
        return self._tokens

    def _lex_identifier_or_keyword(self) -> None:
        start = self._mark()
        self._advance()
        while not self._at_end():
            ch = self._peek()
            if ch.isalnum() or ch == "_":
                self._advance()
                continue
            if ch == ".":
                if self._peek_next() and _is_identifier_continuation(self._peek_next()):
                    self._advance()
                    continue
                self._raise_error("invalid identifier")
            if ch == "-":
                if self._peek_next() and _is_identifier_continuation(self._peek_next()):
                    self._advance()
                    continue
                break
            break

        lexeme = self.source[start.index : self._index]
        if lexeme == "_":
            kind = TokenKind.UNDERSCORE
        else:
            kind = _keyword_kind(lexeme)
            if kind is None:
                if lexeme.endswith(".") or lexeme.endswith("-"):
                    self._raise_error("invalid identifier")
                kind = TokenKind.BOOL_LITERAL if lexeme in {"true", "false"} else TokenKind.IDENTIFIER
        self._tokens.append(
            Token(kind=kind, lexeme=lexeme, span=start.span)
        )

    def _lex_qualified_module_name(self) -> None:
        start = self._mark()
        self._advance()

        if self._at_end() or not _is_identifier_start(self._peek()):
            self._raise_error("invalid module reference")
        self._lex_module_name_segment()

        while not self._at_end() and self._peek() == ".":
            if self._peek_next() is None or not _is_identifier_start(self._peek_next()):
                self._raise_error("invalid module reference")
            self._advance()
            self._lex_module_name_segment()

        lexeme = self.source[start.index : self._index]
        self._tokens.append(
            Token(kind=TokenKind.QUALIFIED_MODULE_NAME, lexeme=lexeme, span=start.span)
        )

    def _lex_module_name_segment(self) -> None:
        self._advance()
        while not self._at_end():
            ch = self._peek()
            if _is_identifier_continuation(ch):
                self._advance()
                continue
            if ch == "-":
                if self._peek_next() and _is_identifier_continuation(self._peek_next()):
                    self._advance()
                    continue
                self._advance()
                continue
            break

    def _lex_number(self) -> None:
        start = self._mark()
        self._advance()
        while not self._at_end() and self._peek().isdigit():
            self._advance()

        kind = TokenKind.INT_LITERAL
        if not self._at_end() and self._peek() == ".":
            if self._peek_next() and self._peek_next().isdigit():
                self._advance()
                while not self._at_end() and self._peek().isdigit():
                    self._advance()
                kind = TokenKind.FLOAT_LITERAL
            else:
                self._raise_error("invalid numeric token")

        if not self._at_end() and (
            self._peek().isalnum() or self._peek() in "._-"
        ):
            self._raise_error("invalid numeric token")

        lexeme = self.source[start.index : self._index]
        self._tokens.append(Token(kind=kind, lexeme=lexeme, span=start.span))

    def _lex_string(self) -> None:
        start = self._mark()
        self._advance()
        chars: list[str] = []

        while not self._at_end():
            ch = self._peek()
            if ch == '"':
                self._advance()
                self._tokens.append(
                    Token(
                        kind=TokenKind.STRING_LITERAL,
                        lexeme="".join(chars),
                        span=start.span,
                    )
                )
                return
            if ch in "\r\n":
                self._raise_error("unterminated string")
            if ch == "\\":
                self._advance()
                if self._at_end():
                    self._raise_error("unterminated string")
                escape = self._peek()
                mapping = {
                    '"': '"',
                    "\\": "\\",
                    "n": "\n",
                    "t": "\t",
                }
                if escape not in mapping:
                    self._raise_error("invalid escape sequence")
                chars.append(mapping[escape])
                self._advance()
                continue
            chars.append(ch)
            self._advance()

        self._raise_error("unterminated string")

    def _consume_comment(self) -> None:
        while not self._at_end() and self._peek() not in "\r\n":
            self._advance()

    def _consume_newline(self) -> None:
        if self._peek() == "\r" and self._peek_next() == "\n":
            self._advance()
        self._advance()
        self._line += 1
        self._column = 1

    def _emit(self, kind: TokenKind, lexeme: str, length: int) -> None:
        start = self._mark()
        for _ in range(length):
            self._advance()
        self._tokens.append(Token(kind=kind, lexeme=lexeme, span=start.span))

    def _match(self, text: str) -> bool:
        return self.source.startswith(text, self._index)

    def _at_end(self) -> bool:
        return self._index >= self._source_len

    def _peek(self) -> str:
        return self.source[self._index]

    def _peek_next(self) -> str | None:
        next_index = self._index + 1
        if next_index >= self._source_len:
            return None
        return self.source[next_index]

    def _advance(self) -> str:
        ch = self.source[self._index]
        self._index += 1
        self._column += 1
        return ch

    def _mark(self) -> "_CursorMark":
        return _CursorMark(
            index=self._index,
            span=SourceSpan(self._line, self._column, self._index),
        )

    def _raise_error(self, message: str) -> None:
        raise LexError(message=message, line=self._line, column=self._column)


@dataclass(frozen=True, slots=True)
class _CursorMark:
    index: int
    span: SourceSpan


def lex(source: str) -> list[Token]:
    return Lexer().tokenize(source)


def _is_identifier_start(ch: str) -> bool:
    return ch == "_" or ch.isalpha()


def _is_identifier_continuation(ch: str) -> bool:
    return ch == "_" or ch.isalnum()


def _keyword_kind(lexeme: str) -> TokenKind | None:
    keywords = {
        "pub": TokenKind.PUB,
        "export": TokenKind.EXPORT,
        "module": TokenKind.MODULE,
        "end-module": TokenKind.END_MODULE,
        "import": TokenKind.IMPORT,
        "include": TokenKind.INCLUDE,
        "dirty": TokenKind.DIRTY,
        "if": TokenKind.IF,
        "else": TokenKind.ELSE,
        "end": TokenKind.END,
        "case": TokenKind.CASE,
        "when": TokenKind.WHEN,
    }
    return keywords.get(lexeme)
