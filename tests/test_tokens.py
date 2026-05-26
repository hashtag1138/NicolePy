from pathlib import Path
import sys

from dataclasses import FrozenInstanceError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.source import (
    BUILTIN_SOURCE_PATH,
    HOST_CONTRACT_SOURCE_PATH,
    MEMORY_SOURCE_PATH,
    SYNTHETIC_SOURCE_PATH,
    SourceFile,
    SourceLocation,
)
from nicole.tokens import SourceSpan, Token, TokenKind


def test_source_span_creation():
    span = SourceSpan(line=2, column=5, offset=12)
    assert span.line == 2
    assert span.column == 5
    assert span.offset == 12


def test_source_span_legacy_constructor_is_zero_length():
    span = SourceSpan(3, 9, 42)
    assert span.start == SourceLocation(line=3, column=9, offset=42)
    assert span.end == SourceLocation(line=3, column=9, offset=42)
    assert span.source.path == SYNTHETIC_SOURCE_PATH


def test_source_span_range_constructor_preserves_compat_accessors():
    source = SourceFile.memory("abc")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=1, offset=0),
        end=SourceLocation(line=1, column=4, offset=3),
    )
    assert span.line == 1
    assert span.column == 1
    assert span.offset == 0
    assert span.source.path == MEMORY_SOURCE_PATH


def test_source_file_memory_and_synthetic_conventions():
    memory = SourceFile.memory("hello")
    synthetic = SourceFile.synthetic()
    builtin = SourceFile.builtin()
    host_contract = SourceFile.host_contract()

    assert memory.path == MEMORY_SOURCE_PATH
    assert memory.text == "hello"
    assert synthetic.path == SYNTHETIC_SOURCE_PATH
    assert synthetic.text is None
    assert builtin.path == BUILTIN_SOURCE_PATH
    assert builtin.text is None
    assert host_contract.path == HOST_CONTRACT_SOURCE_PATH
    assert host_contract.text is None


def test_source_location_and_source_span_are_immutable():
    location = SourceLocation(line=1, column=1, offset=0)
    span = SourceSpan(line=1, column=1, offset=0)

    with pytest.raises(FrozenInstanceError):
        location.line = 2
    with pytest.raises(FrozenInstanceError):
        span.start = SourceLocation(line=1, column=2, offset=1)


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
    assert TokenKind.MODULE.name == "MODULE"
    assert TokenKind.END_MODULE.name == "END_MODULE"
    assert TokenKind.IMPORT.name == "IMPORT"
    assert TokenKind.INCLUDE.name == "INCLUDE"
    assert TokenKind.REQUIRE.name == "REQUIRE"
    assert TokenKind.OPAQUE.name == "OPAQUE"
    assert TokenKind.PURE.name == "PURE"
    assert TokenKind.QUALIFIED_MODULE_PREFIX.name == "QUALIFIED_MODULE_PREFIX"
    assert TokenKind.QUALIFIED_MODULE_NAME.name == "QUALIFIED_MODULE_NAME"
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
