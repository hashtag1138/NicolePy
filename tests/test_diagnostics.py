from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.checker import CheckerError
from nicole.diagnostic_renderer import render_diagnostic, render_diagnostic_error
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


def test_host_abi_error_legacy_message_line_column_and_str_are_compatible() -> None:
    error = HostABIError(message="type is not ABI-compatible in v1: Foo", line=8, column=4)

    assert len(error.diagnostics) == 1
    assert error.diagnostic.phase is DiagnosticPhase.ABI
    assert error.diagnostic.code == "ABI_ERROR"
    assert error.message == "type is not ABI-compatible in v1: Foo"
    assert error.line == 8
    assert error.column == 4
    assert str(error) == "type is not ABI-compatible in v1: Foo"


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


def test_renderer_renders_single_line_excerpt_and_range_marker() -> None:
    source = SourceFile.memory("one\ntwo + three\nend\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=2, column=5, offset=8),
        end=SourceLocation(line=2, column=8, offset=11),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.PARSER,
        code="PARSER_UNEXPECTED_TOKEN",
        message="unexpected token",
        span=span,
    )

    rendered = render_diagnostic(diagnostic)

    assert "ERROR [PARSER/PARSER_UNEXPECTED_TOKEN] unexpected token" in rendered
    assert "--> <memory>:2:5" in rendered
    assert "2 | two + three" in rendered
    assert "  |     ^^^" in rendered


def test_renderer_renders_zero_length_span_with_single_caret() -> None:
    source = SourceFile.memory("abc\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=4, offset=3),
        end=SourceLocation(line=1, column=4, offset=3),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.LEXER,
        code="LEXER_UNEXPECTED_CHARACTER",
        message="unexpected character",
        span=span,
    )

    rendered = render_diagnostic(diagnostic)

    assert "1 | abc" in rendered
    assert "  |    ^" in rendered


def test_renderer_renders_multi_line_ranges() -> None:
    source = SourceFile.memory("aa\nbb\ncc\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=2, offset=1),
        end=SourceLocation(line=3, column=2, offset=7),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.CHECKER,
        code="CHECKER_TYPE_MISMATCH",
        message="type mismatch",
        span=span,
    )

    rendered = render_diagnostic(diagnostic)

    assert "1 | aa" in rendered
    assert "2 | bb" in rendered
    assert "3 | cc" in rendered
    assert "  |  ^" in rendered
    assert "  | ^^" in rendered


def test_renderer_renders_source_less_diagnostic_without_excerpt() -> None:
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.ABI,
        code="ABI_HOST_CONTRACT_REQUIRED",
        message="host contract required for host.* reference: host.log",
    )

    rendered = render_diagnostic(diagnostic)

    assert "ERROR [ABI/ABI_HOST_CONTRACT_REQUIRED] host contract required for host.* reference: host.log" in rendered
    assert "-->" not in rendered
    assert " | " not in rendered


def test_renderer_handles_eof_span_gracefully() -> None:
    source = SourceFile.memory("line\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=2, column=1, offset=5),
        end=SourceLocation(line=2, column=1, offset=5),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.PARSER,
        code="PARSER_UNEXPECTED_EOF",
        message="unexpected end of input",
        span=span,
    )

    rendered = render_diagnostic(diagnostic)

    assert "--> <memory>:2:1" in rendered
    assert "2 | " in rendered
    assert "  | ^" in rendered


def test_renderer_does_not_mutate_diagnostic_or_span() -> None:
    source = SourceFile.memory("x\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=1, offset=0),
        end=SourceLocation(line=1, column=2, offset=1),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.SYMBOLS,
        code="SYMBOLS_DUPLICATE_VISIBLE_NAME",
        message="duplicate visible name: @app.run",
        span=span,
        notes=("n1",),
    )
    before = (diagnostic, diagnostic.notes, diagnostic.span, diagnostic.span.start, diagnostic.span.end)

    _ = render_diagnostic(diagnostic)

    after = (diagnostic, diagnostic.notes, diagnostic.span, diagnostic.span.start, diagnostic.span.end)
    assert after == before


def test_renderer_truncates_large_multi_line_ranges() -> None:
    source = SourceFile.memory("\n".join(f"line-{n}" for n in range(1, 15)))
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=1, offset=0),
        end=SourceLocation(line=14, column=6, offset=90),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.CHECKER,
        code="CHECKER_CASE_BRANCH_STACK_MISMATCH",
        message="case branches have incompatible stack effects",
        span=span,
    )

    rendered = render_diagnostic(diagnostic, max_excerpt_lines=4)

    assert "1 | line-1" in rendered
    assert "2 | line-2" in rendered
    assert "13 | line-13" in rendered
    assert "14 | line-14" in rendered
    assert ". | ..." in rendered


def test_renderer_applies_max_line_length_with_ellipsis_and_aligned_caret() -> None:
    source = SourceFile.memory("0123456789abcdefghijklmnopqrstuvwxyz\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=22, offset=21),
        end=SourceLocation(line=1, column=25, offset=24),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.CHECKER,
        code="CHECKER_WORD_CALL_TYPE_MISMATCH",
        message="type mismatch in word call",
        span=span,
    )

    rendered = render_diagnostic(diagnostic, max_line_length=20)

    assert "1 | ..." in rendered
    assert "..." in rendered.splitlines()[2]
    marker_line = rendered.splitlines()[3]
    assert marker_line.startswith("  | ")
    assert "^^^" in marker_line


def test_renderer_strictly_enforces_small_max_line_length_values() -> None:
    source = SourceFile.memory("0123456789abcdefghijklmnopqrstuvwxyz\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=22, offset=21),
        end=SourceLocation(line=1, column=25, offset=24),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.CHECKER,
        code="CHECKER_WORD_CALL_TYPE_MISMATCH",
        message="type mismatch in word call",
        span=span,
    )

    for width in range(1, 8):
        rendered = render_diagnostic(diagnostic, max_line_length=width)
        rendered_lines = rendered.splitlines()
        excerpt_line = rendered_lines[2]
        marker_line = rendered_lines[3]
        visible_excerpt = excerpt_line.split(" | ", 1)[1]
        visible_marker = marker_line.split(" | ", 1)[1]

        assert len(visible_excerpt) <= width
        assert "l" in visible_excerpt or "m" in visible_excerpt or "n" in visible_excerpt
        assert "^" in visible_marker


def test_renderer_max_line_length_shows_ellipsis_when_there_is_room() -> None:
    source = SourceFile.memory("0123456789abcdefghijklmnopqrstuvwxyz\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=22, offset=21),
        end=SourceLocation(line=1, column=25, offset=24),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.CHECKER,
        code="CHECKER_WORD_CALL_TYPE_MISMATCH",
        message="type mismatch in word call",
        span=span,
    )

    rendered = render_diagnostic(diagnostic, max_line_length=12)
    excerpt_line = rendered.splitlines()[2]
    marker_line = rendered.splitlines()[3]
    visible_excerpt = excerpt_line.split(" | ", 1)[1]

    assert "..." in visible_excerpt
    assert "l" in visible_excerpt or "m" in visible_excerpt or "n" in visible_excerpt
    assert "^" in marker_line


def test_renderer_zero_length_span_retains_visible_context_under_clipping() -> None:
    source = SourceFile.memory("0123456789abcdefghijklmnopqrstuvwxyz\n")
    span = SourceSpan(
        source=source,
        start=SourceLocation(line=1, column=23, offset=22),
        end=SourceLocation(line=1, column=23, offset=22),
    )
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.PARSER,
        code="PARSER_UNEXPECTED_TOKEN",
        message="unexpected token",
        span=span,
    )

    rendered = render_diagnostic(diagnostic, max_line_length=5)
    excerpt_line = rendered.splitlines()[2]
    marker_line = rendered.splitlines()[3]
    visible_excerpt = excerpt_line.split(" | ", 1)[1]

    assert len(visible_excerpt) <= 5
    assert "m" in visible_excerpt
    assert "^" in marker_line


def test_renderer_max_line_length_does_not_affect_source_less_diagnostics() -> None:
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.ABI,
        code="ABI_HOST_CONTRACT_REQUIRED",
        message="host contract required for host.* reference: host.log",
    )

    rendered = render_diagnostic(diagnostic, max_line_length=5)

    assert "ERROR [ABI/ABI_HOST_CONTRACT_REQUIRED] host contract required for host.* reference: host.log" in rendered
    assert "-->" not in rendered
    assert " | " not in rendered


def test_renderer_renders_suggestion_and_notes() -> None:
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        phase=DiagnosticPhase.PARSER,
        code="PARSER_EXPECTED_TOKEN",
        message="expected token",
        suggestion="add the missing token",
        notes=("first note", "second note"),
    )

    rendered = render_diagnostic(diagnostic)

    assert "help: add the missing token" in rendered
    assert "note: first note" in rendered
    assert "note: second note" in rendered


def test_render_diagnostic_error_uses_structured_diagnostic_when_present() -> None:
    error = ParseError(message="unexpected token", line=2, column=4)

    rendered = render_diagnostic_error(error)

    assert "ERROR [PARSER/PARSER_ERROR] unexpected token" in rendered
    assert "-->" not in rendered
