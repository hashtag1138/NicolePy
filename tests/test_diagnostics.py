from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.checker import CheckerError
from nicole.errors import Diagnostic, DiagnosticError, DiagnosticPhase, DiagnosticSeverity
from nicole.host_abi import HostABIError
from nicole.lexer import LexError
from nicole.parser import ParseError
from nicole.resolver import ResolutionError
from nicole.source import SourceFile, SourceLocation
from nicole.standard_symbols import StandardSymbolError
from nicole.symbols import SymbolError
from nicole.tokens import SourceSpan


def test_diagnostic_required_fields() -> None:
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.LEXER,
        code="LEXER_ERROR",
        message="bad token",
    )

    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.phase is DiagnosticPhase.LEXER
    assert diagnostic.code == "LEXER_ERROR"
    assert diagnostic.message == "bad token"


def test_diagnostic_optional_fields_and_derived_source() -> None:
    source = SourceFile.memory("abc")
    start = SourceLocation(line=2, column=4, offset=8)
    end = SourceLocation(line=2, column=7, offset=11)
    span = SourceSpan(source=source, start=start, end=end)
    cause = ValueError("root cause")

    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.PARSER,
        code="PARSER_EXPECTED_TOKEN",
        message="expected token",
        span=span,
        suggestion="add missing token",
        notes=("note-a", "note-b"),
        cause=cause,
    )

    assert diagnostic.span == span
    assert diagnostic.suggestion == "add missing token"
    assert diagnostic.notes == ("note-a", "note-b")
    assert diagnostic.cause is cause
    assert diagnostic.source_file is source
    assert diagnostic.source is source


def test_diagnostic_default_notes_is_empty_tuple() -> None:
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.SYMBOLS,
        code="SYMBOLS_ERROR",
        message="duplicate name",
    )

    assert diagnostic.notes == ()


def test_diagnostic_error_exposes_diagnostics_and_first_diagnostic() -> None:
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.CHECKER,
        code="CHECKER_TYPE_MISMATCH",
        message="type mismatch",
    )
    error = DiagnosticError(diagnostics=(diagnostic,))

    assert error.diagnostics == (diagnostic,)
    assert error.diagnostic is diagnostic
    assert error.message == "type mismatch"


def test_diagnostic_error_rejects_empty_diagnostics() -> None:
    with pytest.raises(ValueError, match="exactly one Diagnostic"):
        DiagnosticError(diagnostics=())


def test_diagnostic_error_rejects_multiple_diagnostics() -> None:
    first = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.LEXER,
        code="LEXER_ERROR",
        message="first",
    )
    second = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.LEXER,
        code="LEXER_ERROR",
        message="second",
    )

    with pytest.raises(ValueError, match="exactly one Diagnostic"):
        DiagnosticError(diagnostics=(first, second))


def test_diagnostic_error_derives_line_and_column_from_span() -> None:
    source = SourceFile.memory("abc")
    start = SourceLocation(line=9, column=3, offset=2)
    end = SourceLocation(line=9, column=5, offset=4)
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.PARSER,
        code="PARSER_EXPECTED_TOKEN",
        message="expected token",
        span=SourceSpan(source=source, start=start, end=end),
    )
    error = DiagnosticError(diagnostic=diagnostic)

    assert error.line == 9
    assert error.column == 3
    assert str(error) == "expected token at 9:3"


def test_legacy_message_line_column_and_str_are_compatible() -> None:
    error = LexError(message="invalid character", line=5, column=11)

    assert len(error.diagnostics) == 1
    assert error.diagnostic.phase is DiagnosticPhase.LEXER
    assert error.diagnostic.code == "LEXER_ERROR"
    assert error.message == "invalid character"
    assert error.line == 5
    assert error.column == 11
    assert str(error) == "invalid character at 5:11"


def test_parse_error_legacy_message_line_column_and_str_are_compatible() -> None:
    error = ParseError(message="unexpected token", line=7, column=2)

    assert len(error.diagnostics) == 1
    assert error.diagnostic.phase is DiagnosticPhase.PARSER
    assert error.diagnostic.code == "PARSER_ERROR"
    assert error.message == "unexpected token"
    assert error.line == 7
    assert error.column == 2
    assert str(error) == "unexpected token at 7:2"


def test_checker_error_legacy_message_line_column_and_str_are_compatible() -> None:
    error = CheckerError(message="insufficient stack", line=4, column=9)

    assert len(error.diagnostics) == 1
    assert error.diagnostic.phase is DiagnosticPhase.CHECKER
    assert error.diagnostic.code == "CHECKER_ERROR"
    assert error.message == "insufficient stack"
    assert error.line == 4
    assert error.column == 9
    assert str(error) == "insufficient stack at 4:9"


def test_locationless_errors_keep_legacy_string_behavior() -> None:
    host_error = HostABIError("type is not ABI-compatible in v1: Foo")
    builtin_error = StandardSymbolError("cannot redefine standard builtin: map.get")

    assert host_error.message == "type is not ABI-compatible in v1: Foo"
    assert builtin_error.message == "cannot redefine standard builtin: map.get"
    assert not hasattr(host_error, "line")
    assert not hasattr(host_error, "column")
    assert not hasattr(builtin_error, "line")
    assert not hasattr(builtin_error, "column")
    assert str(host_error) == "type is not ABI-compatible in v1: Foo"
    assert str(builtin_error) == "cannot redefine standard builtin: map.get"


def test_public_exception_classes_remain_available_and_diagnostic_based() -> None:
    public_exceptions = (
        LexError,
        ParseError,
        SymbolError,
        ResolutionError,
        CheckerError,
        HostABIError,
        StandardSymbolError,
    )

    for exception_type in public_exceptions:
        assert issubclass(exception_type, DiagnosticError)
