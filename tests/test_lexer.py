from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.errors import DiagnosticPhase, DiagnosticSeverity
from nicole.lexer import LexError, lex
from nicole.source import MEMORY_SOURCE_PATH
from nicole.tokens import TokenKind


def test_simple_word_tokenization():
    tokens = lex(": add { a:Int b:Int -- result:Int }\n  a b +\n;")
    kinds = [token.kind for token in tokens]

    assert kinds[0] is TokenKind.COLON
    assert kinds[1] is TokenKind.IDENTIFIER
    assert tokens[1].lexeme == "add"
    assert TokenKind.LBRACE in kinds
    assert TokenKind.STACK_ARROW in kinds
    assert TokenKind.OPERATOR in kinds
    assert kinds[-1] is TokenKind.EOF


def test_quote_start_recognized():
    tokens = lex(":[ | x:Int -- y:Int | x 1 + ;]")

    assert tokens[0].kind is TokenKind.QUOTE_START
    assert tokens[0].lexeme == ":["
    assert any(token.kind is TokenKind.QUOTE_END for token in tokens)
    assert any(token.kind is TokenKind.STACK_ARROW for token in tokens)
    assert tokens[-1].kind is TokenKind.EOF


def test_quote_end_recognized():
    tokens = lex(":[ a:Int | x:Int -- y:Int | x a + ;]")

    assert [token.kind for token in tokens if token.kind is TokenKind.QUOTE_END] == [
        TokenKind.QUOTE_END
    ]


def test_case_arrow_recognized():
    tokens = lex("value case\n  Ok(v) => v\nend")

    kinds = [token.kind for token in tokens]
    assert TokenKind.CASE in kinds
    assert TokenKind.CASE_ARROW in kinds
    assert kinds[-1] is TokenKind.EOF


def test_when_keyword_recognized():
    tokens = lex("value case\n  Ok(v) when v 0 > => v\nend")
    kinds = [token.kind for token in tokens]

    assert TokenKind.CASE in kinds
    assert TokenKind.WHEN in kinds
    assert TokenKind.CASE_ARROW in kinds
    assert kinds[-1] is TokenKind.EOF


def test_dirty_keyword_recognized():
    tokens = lex("dirty : foo { -- } ;")

    assert tokens[0].kind is TokenKind.DIRTY
    assert tokens[0].lexeme == "dirty"


def test_module_keywords_recognized():
    tokens = lex("module end-module import include")

    assert [token.kind for token in tokens] == [
        TokenKind.MODULE,
        TokenKind.END_MODULE,
        TokenKind.IMPORT,
        TokenKind.INCLUDE,
        TokenKind.EOF,
    ]


def test_qualified_module_name_tokenized():
    tokens = lex("@app @app.run @app-")

    assert [token.kind for token in tokens] == [
        TokenKind.QUALIFIED_MODULE_NAME,
        TokenKind.QUALIFIED_MODULE_NAME,
        TokenKind.QUALIFIED_MODULE_NAME,
        TokenKind.EOF,
    ]
    assert [token.lexeme for token in tokens[:-1]] == [
        "@app",
        "@app.run",
        "@app-",
    ]


@pytest.mark.parametrize("source", ["@", "@app.", "@app..run"])
def test_invalid_qualified_module_name_raises(source):
    with pytest.raises(LexError, match="invalid module reference"):
        lex(source)


def test_invalid_module_reference_exposes_structured_diagnostic() -> None:
    with pytest.raises(LexError, match="invalid module reference") as exc_info:
        lex("@")

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.phase is DiagnosticPhase.LEXER
    assert diagnostic.code == "LEXER_INVALID_MODULE_REFERENCE"
    assert diagnostic.message == "invalid module reference"
    assert diagnostic.span is not None
    assert diagnostic.span.start == diagnostic.span.end
    assert error.message == "invalid module reference"
    assert error.line == diagnostic.span.line
    assert error.column == diagnostic.span.column
    assert str(error) == f"invalid module reference at {error.line}:{error.column}"


def test_result_constructors_and_propagation_recognized():
    tokens = lex("1 Ok! MissingKey Err! ?")

    assert [token.kind for token in tokens] == [
        TokenKind.INT_LITERAL,
        TokenKind.RESULT_OK,
        TokenKind.IDENTIFIER,
        TokenKind.RESULT_ERR,
        TokenKind.PROPAGATE,
        TokenKind.EOF,
    ]


def test_comments_ignored():
    tokens = lex("# comment\n: x { -- n:Int } 1 ;")

    assert tokens[0].kind is TokenKind.COLON
    assert all(not token.lexeme.startswith("#") for token in tokens)
    assert tokens[-1].kind is TokenKind.EOF


def test_composite_identifiers():
    tokens = lex("host.log host.read-file list.map app.on-message")

    assert [token.kind for token in tokens[:-1]] == [
        TokenKind.IDENTIFIER,
        TokenKind.IDENTIFIER,
        TokenKind.IDENTIFIER,
        TokenKind.IDENTIFIER,
    ]
    assert [token.lexeme for token in tokens[:-1]] == [
        "host.log",
        "host.read-file",
        "list.map",
        "app.on-message",
    ]


def test_hyphenated_identifier_is_single_identifier():
    tokens = lex("a-b")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENTIFIER,
        TokenKind.EOF,
    ]
    assert [token.lexeme for token in tokens[:-1]] == ["a-b"]


def test_dirty_hyphenated_identifier_is_still_identifier():
    tokens = lex("dirty-int")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENTIFIER,
        TokenKind.EOF,
    ]
    assert [token.lexeme for token in tokens[:-1]] == ["dirty-int"]


def test_dirty_prefixed_identifier_is_still_identifier():
    tokens = lex("mydirtyvalue")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENTIFIER,
        TokenKind.EOF,
    ]
    assert [token.lexeme for token in tokens[:-1]] == ["mydirtyvalue"]


def test_a_b_minus_remains_expression_style():
    tokens = lex("a b -")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENTIFIER,
        TokenKind.IDENTIFIER,
        TokenKind.OPERATOR,
        TokenKind.EOF,
    ]
    assert [token.lexeme for token in tokens[:-1]] == ["a", "b", "-"]


def test_float_operators_are_tokenized_as_distinct_operators():
    tokens = lex("+. -. *. /.")

    assert [token.kind for token in tokens] == [
        TokenKind.OPERATOR,
        TokenKind.OPERATOR,
        TokenKind.OPERATOR,
        TokenKind.OPERATOR,
        TokenKind.EOF,
    ]
    assert [token.lexeme for token in tokens[:-1]] == ["+.", "-.", "*.", "/."]


def test_bare_slash_is_not_a_v1_operator():
    with pytest.raises(LexError):
        lex("/")


def test_string_with_space():
    tokens = lex('"hello world"')

    assert tokens[0].kind is TokenKind.STRING_LITERAL
    assert tokens[0].lexeme == "hello world"
    assert tokens[-1].kind is TokenKind.EOF


def test_string_with_tab_escape():
    tokens = lex('"a\\tb"')

    assert tokens[0].kind is TokenKind.STRING_LITERAL
    assert tokens[0].lexeme == "a\tb"
    assert tokens[-1].kind is TokenKind.EOF


def test_unterminated_string_raises():
    with pytest.raises(LexError):
        lex('"hello world')


@pytest.mark.parametrize("source", ['"\\x"', '"\\q"'])
def test_invalid_escape_sequences_raise(source):
    with pytest.raises(LexError, match="invalid escape sequence"):
        lex(source)


def test_invalid_escape_sequence_exposes_structured_diagnostic() -> None:
    with pytest.raises(LexError, match="invalid escape sequence") as exc_info:
        lex('"\\x"')

    error = exc_info.value
    diagnostic = error.diagnostic

    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.phase is DiagnosticPhase.LEXER
    assert diagnostic.code == "LEXER_INVALID_ESCAPE_SEQUENCE"
    assert diagnostic.message == "invalid escape sequence"
    assert diagnostic.span is not None
    assert diagnostic.span.start == diagnostic.span.end
    assert error.message == "invalid escape sequence"
    assert error.line == diagnostic.span.line
    assert error.column == diagnostic.span.column
    assert str(error) == f"invalid escape sequence at {error.line}:{error.column}"


def test_generic_type_separators():
    tokens = lex("List<Int>")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENTIFIER,
        TokenKind.LT,
        TokenKind.IDENTIFIER,
        TokenKind.GT,
        TokenKind.EOF,
    ]


def test_then_is_not_a_token_kind():
    assert "THEN" not in TokenKind.__members__


def test_lexer_tokens_keep_memory_source_provenance():
    tokens = lex(": add { -- } ;")
    assert all(token.span.source.path == MEMORY_SOURCE_PATH for token in tokens)


def test_lexer_eof_span_is_zero_length():
    tokens = lex("add")
    eof = tokens[-1]

    assert eof.kind is TokenKind.EOF
    assert eof.span.start == eof.span.end


def test_lexer_multiline_positions_use_end_exclusive_ranges():
    tokens = lex("a\nbb")
    first = tokens[0]
    second = tokens[1]
    eof = tokens[2]

    assert first.lexeme == "a"
    assert first.span.start.line == 1
    assert first.span.start.column == 1
    assert first.span.end.line == 1
    assert first.span.end.column == 2
    assert first.span.start.offset == 0
    assert first.span.end.offset == 1

    assert second.lexeme == "bb"
    assert second.span.start.line == 2
    assert second.span.start.column == 1
    assert second.span.end.line == 2
    assert second.span.end.column == 3
    assert second.span.start.offset == 2
    assert second.span.end.offset == 4

    assert eof.span.start == eof.span.end
    assert eof.span.start.line == 2
    assert eof.span.start.column == 3
    assert eof.span.start.offset == 4


def test_lexer_string_span_covers_full_literal_range():
    tokens = lex('"ab"')
    token = tokens[0]

    assert token.kind is TokenKind.STRING_LITERAL
    assert token.lexeme == "ab"
    assert token.span.start.line == 1
    assert token.span.start.column == 1
    assert token.span.end.line == 1
    assert token.span.end.column == 5
    assert token.span.start.offset == 0
    assert token.span.end.offset == 4
