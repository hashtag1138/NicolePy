from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.tokens import SourceSpan, Token, TokenKind


def test_source_span_creation():
    span = SourceSpan(line=2, column=5, offset=12)
    assert span.line == 2
    assert span.column == 5
    assert span.offset == 12


def test_token_creation():
    span = SourceSpan(line=1, column=1, offset=0)
    token = Token(kind=TokenKind.IDENTIFIER, lexeme="add", span=span)
    assert token.kind is TokenKind.IDENTIFIER
    assert token.lexeme == "add"
    assert token.span == span


def test_required_token_kinds_exist():
    assert TokenKind.QUOTE_START.name == "QUOTE_START"
    assert TokenKind.END.name == "END"
    assert TokenKind.DIRTY.name == "DIRTY"
    assert TokenKind.STACK_ARROW.name == "STACK_ARROW"
    assert TokenKind.CASE_ARROW.name == "CASE_ARROW"
    assert TokenKind.EOF.name == "EOF"
    assert TokenKind.LT.name == "LT"
    assert TokenKind.GT.name == "GT"
    assert TokenKind.RESULT_OK.name == "RESULT_OK"
    assert TokenKind.RESULT_ERR.name == "RESULT_ERR"
    assert TokenKind.PROPAGATE.name == "PROPAGATE"


def test_then_is_not_a_token_kind():
    assert "THEN" not in TokenKind.__members__
