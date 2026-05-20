from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.lexer import LexError, lex
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
