from pathlib import Path
import sys
from dataclasses import FrozenInstanceError
import re

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.checker import CheckerError
from nicole.host_abi import HostABIError, HostEffect, HostOpaqueType, HostWord, host_contract_from_words
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.pipeline import analyze_program as _analyze_program
from nicole.resolver import ResolutionError
from nicole.ast_nodes import TypeNode
from nicole.interpreter import NicoleInterpreter
import nicole.runtime as runtime_module
from nicole.runtime import (
    Err,
    Ok,
    RuntimeFrame,
    RuntimeFrameKind,
    RuntimeDiagnostic,
    RuntimeDiagnosticPhase,
    RuntimeDiagnosticSeverity,
    RuntimeError,
    RuntimeHostBindings,
    RuntimeOpaqueValue,
    RuntimeQuote,
    RuntimeStack,
    RuntimeStackTrace,
    UNIT,
    _execute_call,
    _execute_identifier,
    _execute_operator,
    _ensure_matches_type,
    _ensure_supported_map_key,
    render_runtime_diagnostic,
    render_runtime_error,
    runtime_diagnostic,
    run_export,
)
from nicole.source import SourceFile, SourceLocation, SourceSpan


def signature_from_source(source: str):
    return Parser(lex(source)).parse().words[0].signature


def _rewrite_legacy_host_calls_to_bridge_import_aliases(source: str, host_words: list[HostWord]) -> str:
    # Bridge-era runtime fixtures may still contain direct host.* calls; rewrite them
    # to import aliases so resolver invariants match canonical source rules.
    unique_host_names: list[str] = []
    seen = set()
    for host_word in host_words:
        host_name = host_word.name
        if not host_name.startswith("host.") or host_name in seen:
            continue
        seen.add(host_name)
        unique_host_names.append(host_name)

    rewritten = source
    used_aliases: list[tuple[str, str]] = []
    for host_name in sorted(unique_host_names, key=len, reverse=True):
        host_suffix = host_name[len("host.") :]
        alias_name = f"h.{host_suffix}"
        pattern = re.compile(rf"(?<![A-Za-z0-9_@.-]){re.escape(host_name)}(?![A-Za-z0-9_.-])")
        rewritten, count = pattern.subn(alias_name, rewritten)
        if count > 0:
            used_aliases.append((host_name, alias_name))

    if not used_aliases:
        return rewritten

    import_lines = [f"  import @{host_name} as {alias_name}\n" for host_name, alias_name in used_aliases]
    output: list[str] = []
    for line in rewritten.splitlines(keepends=True):
        output.append(line)
        stripped = line.strip()
        if stripped.startswith("module @") and stripped != "module @host":
            output.extend(import_lines)
    return "".join(output)


def analyze_program(source: str, *, host_contract=None):
    if host_contract is None:
        return _analyze_program(source)
    rewritten_source = _rewrite_legacy_host_calls_to_bridge_import_aliases(
        source,
        list(host_contract.words.values()),
    )
    return _analyze_program(rewritten_source, host_contract=host_contract)


def host_contract_with_opaque(*type_names: str, words: list[HostWord] | None = None):
    return host_contract_from_words(
        [] if words is None else words,
        opaque_types=[HostOpaqueType(name=type_name) for type_name in type_names],
    )


def test_runtime_error_string_compatibility_is_preserved() -> None:
    error = RuntimeError("x")

    assert str(error) == "x"
    assert error.message == "x"


def test_runtime_host_bindings_reject_canonical_host_key_during_bridge_freeze() -> None:
    with pytest.raises(RuntimeError, match="runtime host binding must start with 'host.': @host.log"):
        RuntimeHostBindings({"@host.log": lambda _msg: None})


def test_nicole_interpreter_basic_execution() -> None:
    checked = analyze_program(
        """module @app
  : add { a:Int b:Int -- result:Int }
    a b +
  ;
  export : add
end-module
"""
    )
    interpreter = NicoleInterpreter(
        checked=checked,
        runtime_bindings=RuntimeHostBindings({}),
    )

    assert interpreter.run_export("@app.add", 2, 3) == 5


def test_nicole_interpreter_preserves_run_export_behavior() -> None:
    checked = analyze_program(
        """module @app
  : add { a:Int b:Int -- result:Int }
    a b +
  ;
  export : add
end-module
"""
    )
    interpreter = NicoleInterpreter(
        checked=checked,
        runtime_bindings=RuntimeHostBindings({}),
    )

    expected = run_export(checked, "@app.add", RuntimeHostBindings({}), 4, 6)
    assert interpreter.run_export("@app.add", 4, 6) == expected


def test_run_export_wrapper_remains_compatible_with_interpreter_api() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    7
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 7


def test_nicole_interpreter_does_not_expose_runtime_internals() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    1
  ;
  export : run
end-module
"""
    )
    interpreter = NicoleInterpreter(
        checked=checked,
        runtime_bindings=RuntimeHostBindings({}),
    )

    assert hasattr(interpreter, "checked")
    assert hasattr(interpreter, "runtime_bindings")
    assert not hasattr(interpreter, "stack")
    assert not hasattr(interpreter, "trace")
    assert not hasattr(interpreter, "frames")


def test_nicole_interpreter_does_not_persist_runtime_state_between_calls() -> None:
    checked = analyze_program(
        """module @app
  : id { n:Int -- out:Int }
    n
  ;
  export : id
end-module
"""
    )
    interpreter = NicoleInterpreter(
        checked=checked,
        runtime_bindings=RuntimeHostBindings({}),
    )

    assert interpreter.run_export("@app.id", 3) == 3
    assert interpreter.run_export("@app.id", 9) == 9


def test_runtime_frame_creation_with_optional_span() -> None:
    span = SourceSpan(
        source=SourceFile("file.nic", text=""),
        start=SourceLocation(line=1, column=1, offset=0),
        end=SourceLocation(line=1, column=2, offset=1),
    )
    frame_with_span = RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run", span=span)
    frame_without_span = RuntimeFrame(call_kind=RuntimeFrameKind.HOST, name="host.log")

    assert frame_with_span.call_kind is RuntimeFrameKind.WORD
    assert frame_with_span.name == "@app.run"
    assert frame_with_span.span == span
    assert frame_without_span.call_kind is RuntimeFrameKind.HOST
    assert frame_without_span.name == "host.log"
    assert frame_without_span.span is None


def test_runtime_frame_is_immutable() -> None:
    frame = RuntimeFrame(call_kind=RuntimeFrameKind.QUOTATION, name="quote.call")

    with pytest.raises(FrozenInstanceError):
        frame.name = "other"


def test_runtime_stack_trace_empty_constructor() -> None:
    trace = RuntimeStackTrace()

    assert trace.frames == ()
    assert len(trace) == 0
    assert tuple(trace) == ()


def test_runtime_stack_trace_append_returns_new_instance() -> None:
    base = RuntimeStackTrace()
    frame = RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run")

    updated = base.append(frame)

    assert base is not updated
    assert base.frames == ()
    assert updated.frames == (frame,)
    assert len(base) == 0
    assert len(updated) == 1


def test_runtime_stack_trace_extend_returns_new_instance() -> None:
    first = RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.a")
    second = RuntimeFrame(call_kind=RuntimeFrameKind.HOST, name="host.log")
    base = RuntimeStackTrace((first,))

    updated = base.extend((second,))

    assert base is not updated
    assert base.frames == (first,)
    assert updated.frames == (first, second)
    assert tuple(base) == (first,)
    assert tuple(updated) == (first, second)


def test_runtime_stack_trace_iteration_and_len() -> None:
    first = RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.a")
    second = RuntimeFrame(call_kind=RuntimeFrameKind.QUOTATION, name="quote.call")
    trace = RuntimeStackTrace((first, second))

    assert len(trace) == 2
    assert list(trace) == [first, second]


def test_runtime_trace_lifecycle_creates_word_host_and_quotation_frames_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    trace_events: list[tuple[RuntimeStackTrace | None, RuntimeFrame, RuntimeStackTrace]] = []
    original_next_trace = runtime_module._next_trace

    def recording_next_trace(
        current_trace: RuntimeStackTrace | None,
        frame: RuntimeFrame,
    ) -> RuntimeStackTrace:
        new_trace = original_next_trace(current_trace, frame)
        trace_events.append((current_trace, frame, new_trace))
        return new_trace

    monkeypatch.setattr(runtime_module, "_next_trace", recording_next_trace)

    host_signature = signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    "x"
    :[ | msg:String -- out:Int |
      msg host.log
      1
    ;]
    call
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    seen: list[str] = []
    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}))

    assert seen == ["x"]
    assert result == 1

    frame_names = [frame.name for _, frame, _ in trace_events]
    frame_kinds = [frame.call_kind for _, frame, _ in trace_events]
    assert frame_names[:3] == ["@app.run", "quotation", "host:log"]
    assert frame_kinds[:3] == [
        RuntimeFrameKind.WORD,
        RuntimeFrameKind.QUOTATION,
        RuntimeFrameKind.HOST,
    ]

    # each lifecycle step must return a new immutable trace object
    for previous, frame, updated in trace_events:
        if previous is not None:
            assert previous is not updated
            assert len(updated) == len(previous) + 1
            assert previous.frames == updated.frames[:-1]
        assert updated.frames[-1] == frame


def test_runtime_trace_word_frames_remain_compact_for_self_tail_recursion(monkeypatch: pytest.MonkeyPatch) -> None:
    word_frames: list[str] = []
    original_next_trace = runtime_module._next_trace

    def recording_next_trace(
        current_trace: RuntimeStackTrace | None,
        frame: RuntimeFrame,
    ) -> RuntimeStackTrace:
        if frame.call_kind is RuntimeFrameKind.WORD:
            word_frames.append(frame.name)
        return original_next_trace(current_trace, frame)

    monkeypatch.setattr(runtime_module, "_next_trace", recording_next_trace)

    checked = analyze_program(
        """module @app
  : countdown { n:Int -- out:Int }
    n 0 = if
      0
    else
      n 1 - countdown
    end
  ;
  : run { n:Int -- out:Int }
    n countdown
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({}), 2000) == 0

    # direct self-tail recursion keeps lifecycle compact: one frame creation per word entry
    assert word_frames.count("@app.run") == 1
    assert word_frames.count("@app.countdown") == 1


def test_runtime_error_default_diagnostic_is_attached() -> None:
    error = RuntimeError("x")

    assert len(error.diagnostics) == 1
    diagnostic = error.diagnostic
    assert diagnostic.severity is RuntimeDiagnosticSeverity.ERROR
    assert diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert diagnostic.code == "RUNTIME_ERROR"
    assert diagnostic.message == "x"
    assert diagnostic.span is None
    assert diagnostic.trace is None


def test_runtime_error_accepts_explicit_diagnostic() -> None:
    diagnostic = RuntimeDiagnostic(
        severity=RuntimeDiagnosticSeverity.ERROR,
        phase=RuntimeDiagnosticPhase.RUNTIME,
        code="RUNTIME_EXPLICIT",
        message="diagnostic message",
    )
    error = RuntimeError("legacy message", diagnostic=diagnostic)

    assert error.diagnostic is diagnostic
    assert error.diagnostics == (diagnostic,)
    assert str(error) == "legacy message"


def test_runtime_diagnostic_can_carry_trace_data() -> None:
    frame = RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run")
    trace = RuntimeStackTrace((frame,))
    diagnostic = RuntimeDiagnostic(
        severity=RuntimeDiagnosticSeverity.ERROR,
        phase=RuntimeDiagnosticPhase.RUNTIME,
        code="RUNTIME_EXPLICIT_TRACE",
        message="diagnostic message",
        trace=trace,
    )

    assert diagnostic.trace is trace
    assert diagnostic.trace is not None
    assert diagnostic.trace.frames == (frame,)


def test_runtime_diagnostic_helper_builds_expected_object() -> None:
    cause = ValueError("boom")

    diagnostic = runtime_diagnostic(
        code="RUNTIME_STACK_UNDERFLOW",
        message="runtime stack underflow",
        operation="drop",
        suggestion="push before drop",
        notes=["n1", "n2"],
        cause=cause,
    )

    assert diagnostic.severity is RuntimeDiagnosticSeverity.ERROR
    assert diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert diagnostic.code == "RUNTIME_STACK_UNDERFLOW"
    assert diagnostic.message == "runtime stack underflow"
    assert diagnostic.span is None
    assert diagnostic.operation == "drop"
    assert diagnostic.suggestion == "push before drop"
    assert diagnostic.notes == ("n1", "n2")
    assert diagnostic.cause is cause
    assert diagnostic.trace is None


def test_runtime_diagnostic_helper_accepts_trace_data() -> None:
    frame = RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run")
    trace = RuntimeStackTrace((frame,))
    diagnostic = runtime_diagnostic(
        code="RUNTIME_WITH_TRACE",
        message="runtime with trace",
        trace=trace,
    )

    assert diagnostic.trace is trace
    assert diagnostic.trace is not None
    assert diagnostic.trace.frames == (frame,)


def test_runtime_error_preserves_diagnostic_trace_data_and_str_compatibility() -> None:
    frame = RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run")
    trace = RuntimeStackTrace((frame,))
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE",
        message="trace diagnostic",
        trace=trace,
    )
    error = RuntimeError("legacy message", diagnostic=diagnostic)

    assert str(error) == "legacy message"
    assert error.diagnostic.trace is trace
    assert error.diagnostics[0].trace is trace


def test_render_runtime_diagnostic_minimal() -> None:
    diagnostic = runtime_diagnostic(code="RUNTIME_X", message="hello")

    rendered = render_runtime_diagnostic(diagnostic)

    assert rendered == "RuntimeError[RUNTIME_X]\nhello"
    assert "at " not in rendered
    assert "Operation:" not in rendered
    assert "Notes:" not in rendered
    assert "Cause:" not in rendered


def test_render_runtime_diagnostic_with_span() -> None:
    span = SourceSpan(
        source=SourceFile("file.nic", text=""),
        start=SourceLocation(line=42, column=17, offset=0),
        end=SourceLocation(line=42, column=18, offset=1),
    )
    diagnostic = runtime_diagnostic(code="RUNTIME_SPAN", message="with span", span=span)

    rendered = render_runtime_diagnostic(diagnostic)

    assert "RuntimeError[RUNTIME_SPAN]" in rendered
    assert "with span" in rendered
    assert "at file.nic:42:17" in rendered
    assert "^" not in rendered


def test_render_runtime_diagnostic_with_operation() -> None:
    diagnostic = runtime_diagnostic(
        code="RUNTIME_OP",
        message="op message",
        operation="divide",
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert "Operation: divide" in rendered


def test_render_runtime_diagnostic_with_notes() -> None:
    diagnostic = runtime_diagnostic(
        code="RUNTIME_NOTES",
        message="note message",
        notes=("a", "b"),
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert "Notes:" in rendered
    assert "- a" in rendered
    assert "- b" in rendered


def test_render_runtime_diagnostic_with_cause() -> None:
    diagnostic = runtime_diagnostic(
        code="RUNTIME_CAUSE",
        message="cause message",
        cause=ValueError("boom"),
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert "Cause: ValueError: boom" in rendered


def test_render_runtime_diagnostic_with_trace_section_and_order() -> None:
    diagnostic_span = SourceSpan(
        source=SourceFile("diag.nic", text=""),
        start=SourceLocation(line=5, column=7, offset=0),
        end=SourceLocation(line=5, column=8, offset=1),
    )
    frame_span = SourceSpan(
        source=SourceFile("main.nic", text=""),
        start=SourceLocation(line=12, column=3, offset=0),
        end=SourceLocation(line=12, column=4, offset=1),
    )
    trace = RuntimeStackTrace(
        (
            RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),
            RuntimeFrame(call_kind=RuntimeFrameKind.HOST, name="host:print", span=frame_span),
        )
    )
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE_RENDER",
        message="trace remains structured",
        span=diagnostic_span,
        operation="divide",
        notes=("n1",),
        cause=ValueError("boom"),
        trace=trace,
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert rendered.splitlines() == [
        "RuntimeError[RUNTIME_TRACE_RENDER]",
        "trace remains structured",
        "at diag.nic:5:7",
        "Operation: divide",
        "Stack trace:",
        "at @app.run",
        "at host:print (main.nic:12:3)",
        "Notes:",
        "- n1",
        "Cause: ValueError: boom",
    ]


def test_render_runtime_diagnostic_trace_none_renders_nothing_extra() -> None:
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE_NONE",
        message="no trace section",
        trace=None,
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert "Stack trace:" not in rendered


def test_render_runtime_diagnostic_empty_trace_renders_nothing_extra() -> None:
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE_EMPTY",
        message="empty trace section",
        trace=RuntimeStackTrace(),
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert "Stack trace:" not in rendered


def test_render_runtime_diagnostic_trace_frame_without_span_has_no_placeholder() -> None:
    trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE_NO_SPAN",
        message="trace frame without span",
        trace=trace,
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert "at @app.run" in rendered
    assert "at @app.run (" not in rendered


def test_render_runtime_diagnostic_trace_frame_with_span_renders_inline_location() -> None:
    frame_span = SourceSpan(
        source=SourceFile("frame.nic", text=""),
        start=SourceLocation(line=3, column=9, offset=0),
        end=SourceLocation(line=3, column=10, offset=1),
    )
    trace = RuntimeStackTrace(
        (RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run", span=frame_span),)
    )
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE_WITH_SPAN",
        message="trace frame with span",
        trace=trace,
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert "at @app.run (frame.nic:3:9)" in rendered


def test_render_runtime_error_uses_attached_diagnostic_and_preserves_str() -> None:
    diagnostic = runtime_diagnostic(code="RUNTIME_ERR", message="diag message")
    error = RuntimeError("legacy message", diagnostic=diagnostic)

    rendered = render_runtime_error(error)

    assert rendered.startswith("RuntimeError[RUNTIME_ERR]")
    assert "diag message" in rendered
    assert str(error) == "legacy message"


def test_render_runtime_error_includes_trace_via_diagnostic() -> None:
    trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))
    diagnostic = runtime_diagnostic(
        code="RUNTIME_ERR_TRACE",
        message="diag trace message",
        trace=trace,
    )
    error = RuntimeError("legacy message", diagnostic=diagnostic)

    rendered = render_runtime_error(error)

    assert "Stack trace:" in rendered
    assert "at @app.run" in rendered
    assert str(error) == "legacy message"


def test_render_runtime_diagnostic_is_deterministic() -> None:
    diagnostic = runtime_diagnostic(
        code="RUNTIME_DETERMINISTIC",
        message="deterministic",
        operation="divide",
        notes=("n1",),
    )

    first = render_runtime_diagnostic(diagnostic)
    second = render_runtime_diagnostic(diagnostic)

    assert first == second


def test_render_runtime_diagnostic_trace_order_is_deterministic() -> None:
    trace = RuntimeStackTrace(
        (
            RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.outer"),
            RuntimeFrame(call_kind=RuntimeFrameKind.QUOTATION, name="quotation"),
            RuntimeFrame(call_kind=RuntimeFrameKind.HOST, name="host:print"),
        )
    )
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE_ORDER",
        message="trace order",
        trace=trace,
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert rendered.splitlines() == [
        "RuntimeError[RUNTIME_TRACE_ORDER]",
        "trace order",
        "Stack trace:",
        "at @app.outer",
        "at quotation",
        "at host:print",
    ]


def test_render_runtime_diagnostic_does_not_mutate() -> None:
    diagnostic = runtime_diagnostic(
        code="RUNTIME_IMMUTABLE",
        message="immutable",
        notes=("n1", "n2"),
    )

    before = diagnostic
    _ = render_runtime_diagnostic(diagnostic)

    assert diagnostic == before


def test_render_runtime_diagnostic_does_not_mutate_trace() -> None:
    frame = RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run")
    trace = RuntimeStackTrace((frame,))
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE_IMMUTABLE",
        message="trace immutable",
        trace=trace,
    )

    before_frames = trace.frames
    _ = render_runtime_diagnostic(diagnostic)

    assert trace.frames == before_frames


def test_render_runtime_diagnostic_trace_rendering_remains_ansi_free() -> None:
    trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))
    diagnostic = runtime_diagnostic(
        code="RUNTIME_TRACE_ANSI",
        message="ansi free",
        trace=trace,
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert "\x1b[" not in rendered


def test_render_runtime_diagnostic_does_not_leak_opaque_payload() -> None:
    secret_payload = "secret-render-payload"
    _opaque = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload=secret_payload)
    diagnostic = runtime_diagnostic(
        code="RUNTIME_OPAQUE",
        message="opaque failure",
        notes=("safe note",),
    )

    rendered = render_runtime_diagnostic(diagnostic)

    assert secret_payload not in rendered


def test_runtime_missing_export_error_has_structured_diagnostic() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    1
  ;
  export : run
end-module
"""
    )

    with pytest.raises(RuntimeError, match="missing export: @app.missing") as exc_info:
        run_export(checked, "@app.missing", RuntimeHostBindings({}))

    error = exc_info.value
    assert str(error) == "missing export: @app.missing"
    assert error.diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert error.diagnostic.code == "RUNTIME_MISSING_EXPORT"


def test_runtime_division_by_zero_has_structured_diagnostic() -> None:
    stack = RuntimeStack()
    stack.push(1)
    stack.push(0)

    with pytest.raises(RuntimeError, match="runtime arithmetic error: div by zero") as exc_info:
        _execute_operator("div", stack)

    error = exc_info.value
    assert str(error) == "runtime arithmetic error: div by zero"
    assert error.diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert error.diagnostic.code == "RUNTIME_DIVISION_BY_ZERO"
    assert error.diagnostic.message == "runtime arithmetic error: div by zero"


def test_runtime_division_by_zero_via_execution_attaches_trace() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    1 0 div
  ;
  export : run
end-module
"""
    )

    with pytest.raises(RuntimeError, match="runtime arithmetic error: div by zero") as exc_info:
        run_export(checked, "@app.run", RuntimeHostBindings({}))

    error = exc_info.value
    assert error.diagnostic.code == "RUNTIME_DIVISION_BY_ZERO"
    assert error.diagnostic.trace is not None
    assert error.diagnostic.trace.frames[0].call_kind is RuntimeFrameKind.WORD
    assert error.diagnostic.trace.frames[0].name == "@app.run"


def test_runtime_host_failure_keeps_message_and_attaches_cause() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- }
    "hello" host.log
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    def boom(msg: str) -> None:
        raise ValueError("boom")

    runtime = RuntimeHostBindings({"host.log": boom})
    with pytest.raises(RuntimeError, match="runtime host error: host.log") as exc_info:
        run_export(checked, "@app.run", runtime)

    error = exc_info.value
    assert str(error) == "runtime host error: host.log"
    assert isinstance(error.diagnostic.cause, ValueError)
    assert error.diagnostic.code == "RUNTIME_HOST_FAILURE"
    assert isinstance(error.__cause__, ValueError)
    assert error.diagnostic.trace is not None
    assert error.diagnostic.trace.frames[-1].call_kind is RuntimeFrameKind.HOST
    assert error.diagnostic.trace.frames[-1].name == "host:log"


def test_runtime_stack_underflow_error_has_structured_diagnostic_without_span() -> None:
    with pytest.raises(RuntimeError, match="runtime stack underflow") as exc_info:
        RuntimeStack().pop()

    error = exc_info.value
    assert error.diagnostic.code == "RUNTIME_STACK_UNDERFLOW"
    assert error.diagnostic.span is None


def test_runtime_invalid_comparison_has_diagnostic_context() -> None:
    span = SourceSpan(
        source=SourceFile("main.nic", text=""),
        start=SourceLocation(line=7, column=5, offset=0),
        end=SourceLocation(line=7, column=6, offset=1),
    )
    trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))
    stack = RuntimeStack()
    stack.push(1)
    stack.push(2.0)

    with pytest.raises(
        RuntimeError,
        match="wrong runtime signature for comparison operands: expected Int/Int or Float/Float",
    ) as exc_info:
        _execute_operator("<", stack, span=span, current_trace=trace)

    error = exc_info.value
    assert str(error) == "wrong runtime signature for comparison operands: expected Int/Int or Float/Float"
    assert error.diagnostic.code == "RUNTIME_INVALID_COMPARISON"
    assert error.diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert error.diagnostic.operation == "compare"
    assert error.diagnostic.span == span
    assert error.diagnostic.trace is trace


def test_runtime_invalid_quotation_has_diagnostic_context() -> None:
    parsed = Parser(
        lex(
            """module @app
  : run { -- }
    1 call
  ;
end-module
"""
        )
    ).parse()
    call_op = parsed.words[0].body.items[1]

    stack = RuntimeStack()
    stack.push(1)
    with pytest.raises(RuntimeError, match="call expects runtime quotation") as exc_info:
        _execute_call({}, stack, {}, RuntimeHostBindings({}), span=call_op.span)

    error = exc_info.value
    assert str(error) == "call expects runtime quotation"
    assert error.diagnostic.code == "RUNTIME_INVALID_QUOTATION"
    assert error.diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert error.diagnostic.operation == "call"
    assert error.diagnostic.span == call_op.span


def test_runtime_unsupported_operation_has_diagnostic_context() -> None:
    with pytest.raises(RuntimeError, match="runtime feature not supported: operator pow") as exc_info:
        _execute_operator("pow", RuntimeStack())

    error = exc_info.value
    assert str(error) == "runtime feature not supported: operator pow"
    assert error.diagnostic.code == "RUNTIME_UNSUPPORTED_OPERATION"
    assert error.diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert error.diagnostic.operation == "pow"
    assert error.diagnostic.span is None


def test_runtime_type_error_has_diagnostic_context() -> None:
    stack = RuntimeStack()
    stack.push(1)
    stack.push(2)
    with pytest.raises(RuntimeError, match="wrong runtime signature for left operand: expected Bool") as exc_info:
        _execute_operator("and", stack)

    error = exc_info.value
    assert str(error) == "wrong runtime signature for left operand: expected Bool"
    assert error.diagnostic.code == "RUNTIME_RUNTIME_TYPE_ERROR"
    assert error.diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert error.diagnostic.operation == "and"
    assert error.diagnostic.span is None


def test_runtime_word_input_type_mismatch_attaches_word_trace() -> None:
    checked = analyze_program(
        """module @app
  : run { n:Int -- out:Int }
    n
  ;
  export : run
end-module
"""
    )

    with pytest.raises(RuntimeError, match="wrong runtime signature for input 'n': expected Int") as exc_info:
        run_export(checked, "@app.run", RuntimeHostBindings({}), True)

    error = exc_info.value
    assert error.diagnostic.code == "RUNTIME_RUNTIME_TYPE_ERROR"
    assert error.diagnostic.trace is not None
    assert error.diagnostic.trace.frames[-1].call_kind is RuntimeFrameKind.WORD
    assert error.diagnostic.trace.frames[-1].name == "@app.run"


def test_runtime_host_output_type_mismatch_attaches_host_trace() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { -- out:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.out", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- out:Int }
    host.out
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    with pytest.raises(RuntimeError, match="wrong runtime signature for host output 'out': expected Int") as exc_info:
        run_export(checked, "@app.run", RuntimeHostBindings({"host.out": lambda: "x"}))

    error = exc_info.value
    assert error.diagnostic.code == "RUNTIME_RUNTIME_TYPE_ERROR"
    assert error.diagnostic.trace is not None
    assert error.diagnostic.trace.frames[-1].call_kind is RuntimeFrameKind.HOST
    assert error.diagnostic.trace.frames[-1].name == "host:out"


def test_runtime_quotation_output_type_mismatch_attaches_quotation_trace() -> None:
    quote_trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.QUOTATION, name="quotation"),))

    with pytest.raises(RuntimeError, match="wrong runtime signature for quotation output 'out': expected Int") as exc_info:
        _ensure_matches_type(
            "x",
            "Int",
            context="quotation output 'out'",
            trace=quote_trace,
        )

    error = exc_info.value
    assert error.diagnostic.code == "RUNTIME_RUNTIME_TYPE_ERROR"
    assert error.diagnostic.trace is quote_trace
    assert error.diagnostic.trace.frames[-1].call_kind is RuntimeFrameKind.QUOTATION


def test_runtime_builtin_type_mismatch_attaches_word_trace() -> None:
    word_trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))

    with pytest.raises(RuntimeError, match="wrong runtime signature for list.len input: expected List") as exc_info:
        _ensure_matches_type(
            1,
            "List",
            context="list.len input",
            trace=word_trace,
        )

    error = exc_info.value
    assert error.diagnostic.trace is word_trace
    assert error.diagnostic.trace.frames[-1].name == "@app.run"


def test_runtime_map_key_validation_error_attaches_word_trace() -> None:
    word_trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))

    with pytest.raises(
        RuntimeError,
        match="wrong runtime signature for map.contains key: expected Int/String/Bool",
    ) as exc_info:
        _ensure_supported_map_key(1.5, context="map.contains key", trace=word_trace)

    error = exc_info.value
    assert error.diagnostic.trace is word_trace
    assert error.diagnostic.trace.frames[-1].name == "@app.run"


def test_runtime_propagate_input_type_mismatch_attaches_word_trace() -> None:
    word_trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))

    with pytest.raises(RuntimeError, match="wrong runtime signature for \\? input: expected Result") as exc_info:
        _ensure_matches_type(
            1,
            "Result",
            context="? input",
            trace=word_trace,
        )

    error = exc_info.value
    assert error.diagnostic.trace is word_trace
    assert error.diagnostic.trace.frames[-1].name == "@app.run"


def test_runtime_if_condition_type_mismatch_attaches_word_trace() -> None:
    word_trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))

    with pytest.raises(RuntimeError, match="wrong runtime signature for if condition: expected Bool") as exc_info:
        _ensure_matches_type(
            1,
            "Bool",
            context="if condition",
            trace=word_trace,
        )

    error = exc_info.value
    assert error.diagnostic.trace is word_trace
    assert error.diagnostic.trace.frames[-1].name == "@app.run"


def test_runtime_quotation_capture_type_mismatch_attaches_word_trace() -> None:
    word_trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))

    with pytest.raises(
        RuntimeError,
        match="wrong runtime signature for quotation capture 'captured': expected Int",
    ) as exc_info:
        _ensure_matches_type(
            "x",
            "Int",
            context="quotation capture 'captured'",
            trace=word_trace,
        )

    error = exc_info.value
    assert error.diagnostic.trace is word_trace
    assert error.diagnostic.trace.frames[-1].name == "@app.run"


def test_runtime_unsupported_nested_list_type_error_carries_trace() -> None:
    trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))
    unsupported_list_type = TypeNode(
        span=SourceSpan(line=0, column=0, offset=0),
        name="List",
        args=(),
    )

    with pytest.raises(RuntimeError, match="runtime feature not supported: type List") as exc_info:
        _ensure_matches_type(
            (),
            unsupported_list_type,
            context="unsupported nested type",
            trace=trace,
        )

    error = exc_info.value
    assert error.diagnostic.code == "RUNTIME_UNSUPPORTED_OPERATION"
    assert error.diagnostic.trace is trace


def test_runtime_bridge_compat_valid_host_call() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

    seen: list[str] = []

    checked = analyze_program(
        """module @app
  : run { -- }
    "hello" host.log
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)})
    result = run_export(checked, "@app.run", runtime)

    assert result is None
    assert seen == ["hello"]


def test_runtime_drop_underflow() -> None:
    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("drop", RuntimeStack())


def test_runtime_dup_underflow() -> None:
    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("dup", RuntimeStack())


def test_runtime_swap_underflow() -> None:
    stack = RuntimeStack()
    stack.push(1)

    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("swap", stack)


def test_runtime_over_underflow() -> None:
    stack = RuntimeStack()
    stack.push(1)

    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("over", stack)


def test_runtime_rot_underflow() -> None:
    stack = RuntimeStack()
    stack.push(1)
    stack.push(2)

    with pytest.raises(RuntimeError, match="runtime stack underflow"):
        _execute_operator("rot", stack)


def test_runtime_bridge_compat_missing_host_binding() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- }
    "hello" host.log
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({})
    with pytest.raises(RuntimeError, match="missing host binding: host.log"):
        run_export(checked, "@app.run", runtime)


def test_runtime_host_callable_exception_is_normalized() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- }
    "hello" host.log
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    def boom(msg: str) -> None:
        raise ValueError("boom")

    runtime = RuntimeHostBindings({"host.log": boom})
    with pytest.raises(RuntimeError, match="runtime host error: host.log"):
        run_export(checked, "@app.run", runtime)


def test_runtime_missing_export() -> None:
    checked = analyze_program("""module @app
  : run { -- n:Int }
    1
  ;
  export : run
end-module
""")

    with pytest.raises(RuntimeError, match="missing export: @app.missing"):
        run_export(checked, "@app.missing", RuntimeHostBindings({}))


def test_runtime_wrong_arity() -> None:
    checked = analyze_program(
        """module @app
  : add { a:Int b:Int -- result:Int }
    a b +
  ;
  export : add
end-module
"""
    )

    with pytest.raises(RuntimeError, match="wrong arity"):
        run_export(checked, "@app.add", RuntimeHostBindings({}), 1)

    with pytest.raises(RuntimeError, match="wrong arity"):
        run_export(checked, "@app.add", RuntimeHostBindings({}), 1, 2, 3)


def test_runtime_wrong_runtime_signature() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { -- n:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.random-int", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    host.random-int
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.random-int": lambda: "not-an-int"})
    with pytest.raises(RuntimeError, match="wrong runtime signature"):
        run_export(checked, "@app.run", runtime)


def test_runtime_accepts_host_opaque_wrapper_for_host_input_output() -> None:
    host_signature = signature_from_source("""module @app
  : hostecho { fh:host.io.FileHandle -- out:host.io.FileHandle } ;
end-module
""")
    host_contract = host_contract_with_opaque(
        "host.io.FileHandle",
        words=[HostWord(name="host.echo-handle", signature=host_signature, effect=HostEffect.PURE)],
    )
    checked = analyze_program(
        """module @app
  : run { fh:host.io.FileHandle -- out:host.io.FileHandle }
    fh host.echo-handle
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    handle = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload={"fd": 3})
    runtime = RuntimeHostBindings({"host.echo-handle": lambda fh: fh})
    result = run_export(checked, "@app.run", runtime, handle)

    assert result == handle


def test_runtime_accepts_host_opaque_wrapper_for_export_input_output() -> None:
    checked = analyze_program(
        """module @app
  : run { fh:host.io.FileHandle -- out:host.io.FileHandle }
    fh
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    handle = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload="opaque")
    result = run_export(checked, "@app.run", RuntimeHostBindings({}), handle)

    assert result == handle


def test_runtime_accepts_host_opaque_wrapper_for_quotation_capture_input_output() -> None:
    checked = analyze_program(
        """module @app
  : run { captured:host.io.FileHandle x:host.io.FileHandle -- out:host.io.FileHandle }
    x
    captured
    :[ c:host.io.FileHandle | i:host.io.FileHandle -- o:host.io.FileHandle |
      c drop
      i
    ;]
    call
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    captured = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload={"id": "cap"})
    value = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload={"id": "in"})
    result = run_export(checked, "@app.run", RuntimeHostBindings({}), captured, value)

    assert result == value


def test_runtime_accepts_host_opaque_wrapper_in_list() -> None:
    checked = analyze_program(
        """module @app
  : run { xs:List<host.io.FileHandle> -- ys:List<host.io.FileHandle> }
    xs
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    values = (
        RuntimeOpaqueValue(type_name="host.io.FileHandle", payload=1),
        RuntimeOpaqueValue(type_name="host.io.FileHandle", payload=2),
    )
    result = run_export(checked, "@app.run", RuntimeHostBindings({}), values)

    assert result == values


def test_runtime_accepts_host_opaque_wrapper_in_result_value() -> None:
    checked = analyze_program(
        """module @app
  : run { r:Result<host.io.FileHandle,String> -- out:Result<host.io.FileHandle,String> }
    r
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    result_value = Ok(RuntimeOpaqueValue(type_name="host.io.FileHandle", payload="ok"))
    result = run_export(checked, "@app.run", RuntimeHostBindings({}), result_value)

    assert result == result_value


def test_runtime_accepts_host_opaque_wrapper_in_result_error() -> None:
    checked = analyze_program(
        """module @app
  : run { r:Result<String,host.io.FileHandle> -- out:Result<String,host.io.FileHandle> }
    r
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    result_value = Err(RuntimeOpaqueValue(type_name="host.io.FileHandle", payload="err"))
    result = run_export(checked, "@app.run", RuntimeHostBindings({}), result_value)

    assert result == result_value


def test_runtime_accepts_host_opaque_wrapper_in_map_string_value() -> None:
    checked = analyze_program(
        """module @app
  : run { m:Map<String,host.io.FileHandle> -- out:Map<String,host.io.FileHandle> }
    m
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    value = {"file": RuntimeOpaqueValue(type_name="host.io.FileHandle", payload=11)}
    result = run_export(checked, "@app.run", RuntimeHostBindings({}), value)

    assert result == value


def test_runtime_accepts_host_opaque_wrapper_in_map_int_value() -> None:
    checked = analyze_program(
        """module @app
  : run { m:Map<Int,host.io.FileHandle> -- out:Map<Int,host.io.FileHandle> }
    m
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    value = {1: RuntimeOpaqueValue(type_name="host.io.FileHandle", payload=12)}
    result = run_export(checked, "@app.run", RuntimeHostBindings({}), value)

    assert result == value


def test_runtime_accepts_host_opaque_wrapper_in_map_bool_value() -> None:
    checked = analyze_program(
        """module @app
  : run { m:Map<Bool,host.io.FileHandle> -- out:Map<Bool,host.io.FileHandle> }
    m
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    value = {True: RuntimeOpaqueValue(type_name="host.io.FileHandle", payload=13)}
    result = run_export(checked, "@app.run", RuntimeHostBindings({}), value)

    assert result == value


def test_runtime_rejects_host_opaque_wrapper_with_wrong_type_name() -> None:
    checked = analyze_program(
        """module @app
  : run { fh:host.io.FileHandle -- out:host.io.FileHandle }
    fh
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle", "host.net.TcpSocket"),
    )

    wrong = RuntimeOpaqueValue(type_name="host.net.TcpSocket", payload="bad")
    with pytest.raises(RuntimeError, match="expected host.io.FileHandle"):
        run_export(checked, "@app.run", RuntimeHostBindings({}), wrong)


def test_runtime_rejects_malformed_host_opaque_wrapper() -> None:
    checked = analyze_program(
        """module @app
  : run { fh:host.io.FileHandle -- out:host.io.FileHandle }
    fh
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    malformed = RuntimeOpaqueValue(type_name=123, payload="bad")  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="expected host.io.FileHandle"):
        run_export(checked, "@app.run", RuntimeHostBindings({}), malformed)


def test_runtime_rejects_raw_python_object_for_host_opaque_type() -> None:
    checked = analyze_program(
        """module @app
  : run { fh:host.io.FileHandle -- out:host.io.FileHandle }
    fh
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle"),
    )

    with pytest.raises(RuntimeError, match="expected host.io.FileHandle"):
        run_export(checked, "@app.run", RuntimeHostBindings({}), object())


def test_runtime_rejects_file_handle_when_tcp_socket_expected() -> None:
    checked = analyze_program(
        """module @app
  : run { socket:host.net.TcpSocket -- out:host.net.TcpSocket }
    socket
  ;
  export : run
end-module
""",
        host_contract=host_contract_with_opaque("host.io.FileHandle", "host.net.TcpSocket"),
    )

    file_handle = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload="fd")
    with pytest.raises(RuntimeError, match="expected host.net.TcpSocket"):
        run_export(checked, "@app.run", RuntimeHostBindings({}), file_handle)


def test_runtime_rejects_equality_on_host_opaque_values() -> None:
    span = SourceSpan(
        source=SourceFile("main.nic", text=""),
        start=SourceLocation(line=11, column=3, offset=0),
        end=SourceLocation(line=11, column=4, offset=1),
    )
    trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))
    secret_payload = "secret-token-opaque"
    a = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload=secret_payload)
    b = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload=secret_payload)
    stack = RuntimeStack()
    stack.push(a)
    stack.push(b)

    with pytest.raises(RuntimeError, match="equality is not supported for host opaque values") as exc_info:
        _execute_operator("=", stack, span=span, current_trace=trace)

    error = exc_info.value
    assert str(error) == "equality is not supported for host opaque values"
    assert error.diagnostic.code == "RUNTIME_INVALID_COMPARISON"
    assert error.diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert error.diagnostic.operation == "compare"
    assert error.diagnostic.span == span
    assert error.diagnostic.trace is trace
    assert secret_payload not in error.diagnostic.message
    assert all(secret_payload not in note for note in error.diagnostic.notes)


def test_runtime_rejects_inequality_on_host_opaque_values() -> None:
    span = SourceSpan(
        source=SourceFile("main.nic", text=""),
        start=SourceLocation(line=12, column=3, offset=0),
        end=SourceLocation(line=12, column=5, offset=2),
    )
    trace = RuntimeStackTrace((RuntimeFrame(call_kind=RuntimeFrameKind.WORD, name="@app.run"),))
    a = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload="a")
    b = RuntimeOpaqueValue(type_name="host.io.FileHandle", payload="b")
    stack = RuntimeStack()
    stack.push(a)
    stack.push(b)
    with pytest.raises(RuntimeError, match="equality is not supported for host opaque values") as exc_info:
        _execute_operator("!=", stack, span=span, current_trace=trace)

    error = exc_info.value
    assert error.diagnostic.code == "RUNTIME_INVALID_COMPARISON"
    assert error.diagnostic.phase is RuntimeDiagnosticPhase.RUNTIME
    assert error.diagnostic.operation == "compare"
    assert error.diagnostic.span == span
    assert error.diagnostic.trace is trace


def test_runtime_typed_arithmetic_export() -> None:
    checked = analyze_program(
        """module @app
  : add { a:Int b:Int -- result:Int }
    a b +
  ;
  export : add
end-module
"""
    )

    result = run_export(checked, "@app.add", RuntimeHostBindings({}), 2, 3)

    assert result == 5


def test_runtime_comparison_operators_execute() -> None:
    checked = analyze_program(
        """module @app
  : lt-int { -- b:Bool }
    1 2 <
  ;
  : ge-float { -- b:Bool }
    2.0 3.0 >=
  ;
  : eq { -- b:Bool }
    3 3 =
  ;
  : ne { -- b:Bool }
    3 4 !=
  ;
  export : lt-int
  export : ge-float
  export : eq
  export : ne
end-module
"""
    )

    assert run_export(checked, "@app.lt-int", RuntimeHostBindings({})) is True
    assert run_export(checked, "@app.ge-float", RuntimeHostBindings({})) is False
    assert run_export(checked, "@app.eq", RuntimeHostBindings({})) is True
    assert run_export(checked, "@app.ne", RuntimeHostBindings({})) is True


def test_runtime_boolean_operators_execute() -> None:
    checked = analyze_program(
        """module @app
  : andv { -- b:Bool }
    true false and
  ;
  : orv { -- b:Bool }
    true false or
  ;
  : not-true { -- b:Bool }
    true not
  ;
  : not-false { -- b:Bool }
    false not
  ;
  export : andv
  export : orv
  export : not-true
  export : not-false
end-module
"""
    )

    assert run_export(checked, "@app.andv", RuntimeHostBindings({})) is False
    assert run_export(checked, "@app.orv", RuntimeHostBindings({})) is True
    assert run_export(checked, "@app.not-true", RuntimeHostBindings({})) is False
    assert run_export(checked, "@app.not-false", RuntimeHostBindings({})) is True


def test_runtime_boolean_operators_reject_non_bool() -> None:
    stack = RuntimeStack()
    stack.push(1)
    stack.push(2)
    with pytest.raises(RuntimeError, match="expected Bool"):
        _execute_operator("and", stack)

    stack = RuntimeStack()
    stack.push(1)
    with pytest.raises(RuntimeError, match="expected Bool"):
        _execute_operator("not", stack)


def test_runtime_over_and_rot_execute() -> None:
    checked = analyze_program(
        """module @app
  : over { -- a:Int b:Int c:Int }
    1 2 over
  ;
  : rot { -- a:Int b:Int c:Int }
    1 2 3 rot
  ;
  export : over
  export : rot
end-module
"""
    )

    assert run_export(checked, "@app.over", RuntimeHostBindings({})) == (1, 2, 1)
    assert run_export(checked, "@app.rot", RuntimeHostBindings({})) == (2, 3, 1)


def test_runtime_division_by_zero_is_normalized() -> None:
    checked = analyze_program("""module @app
  : run { -- n:Int }
    1 0 div
  ;
  export : run
end-module
""")

    with pytest.raises(RuntimeError, match="runtime arithmetic error: div by zero"):
        run_export(checked, "@app.run", RuntimeHostBindings({}))


def test_runtime_modulo_by_zero_is_normalized() -> None:
    checked = analyze_program("""module @app
  : run { -- n:Int }
    1 0 mod
  ;
  export : run
end-module
""")

    with pytest.raises(RuntimeError, match="runtime arithmetic error: mod by zero"):
        run_export(checked, "@app.run", RuntimeHostBindings({}))


def test_runtime_float_division_by_zero_is_normalized() -> None:
    checked = analyze_program("""module @app
  : run { -- n:Float }
    1.0 0.0 /.
  ;
  export : run
end-module
""")

    with pytest.raises(RuntimeError, match="runtime arithmetic error: /\\. by zero"):
        run_export(checked, "@app.run", RuntimeHostBindings({}))


def test_runtime_nicole_word_calling_host_word() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

    seen: list[str] = []
    checked = analyze_program(
        """module @app
  : log-it { msg:String -- }
    msg host.log
  ;
  : run { -- }
    "hello" log-it
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)})
    run_export(checked, "@app.run", runtime)

    assert seen == ["hello"]


def test_runtime_nested_nicole_word_calls() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

    seen: list[str] = []
    checked = analyze_program(
        """module @app
  : inner { msg:String -- }
    msg host.log
  ;
  : middle { msg:String -- }
    msg inner
  ;
  : run { -- }
    "hello" middle
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)})
    run_export(checked, "@app.run", runtime)

    assert seen == ["hello"]


def test_runtime_self_tail_call_countdown_beyond_python_recursion_depth() -> None:
    checked = analyze_program(
        """module @app
  : countdown { n:Int -- out:Int }
    n 0 = if
      0
    else
      n 1 - countdown
    end
  ;
  : run { n:Int -- out:Int }
    n countdown
  ;
  export : run
end-module
"""
    )

    depth = sys.getrecursionlimit() + 1000
    assert run_export(checked, "@app.run", RuntimeHostBindings({}), depth) == 0


def test_runtime_self_tail_call_accumulator_style_beyond_python_recursion_depth() -> None:
    checked = analyze_program(
        """module @app
  : sum-down-acc { n:Int acc:Int -- result:Int }
    n 0 = if
      acc
    else
      n 1 - acc n + sum-down-acc
    end
  ;
  : run { n:Int -- result:Int }
    n 0 sum-down-acc
  ;
  export : run
end-module
"""
    )

    depth = sys.getrecursionlimit() + 1000
    assert run_export(checked, "@app.run", RuntimeHostBindings({}), depth) == depth * (depth + 1) // 2


def test_runtime_non_tail_recursion_remains_unoptimized() -> None:
    checked = analyze_program(
        """module @app
  : non-tail { n:Int -- out:Int }
    n 0 = if
      0
    else
      n 1 - non-tail 1 +
    end
  ;
  : run { n:Int -- out:Int }
    n non-tail
  ;
  export : run
end-module
"""
    )

    depth = sys.getrecursionlimit() + 200
    with pytest.raises(RecursionError):
        run_export(checked, "@app.run", RuntimeHostBindings({}), depth)


def test_runtime_mutual_recursion_remains_unoptimized() -> None:
    checked = analyze_program(
        """module @app
  : even { n:Int -- out:Int }
    n 0 = if
      0
    else
      n 1 - odd
    end
  ;
  : odd { n:Int -- out:Int }
    n 0 = if
      1
    else
      n 1 - even
    end
  ;
  : run { n:Int -- out:Int }
    n even
  ;
  export : run
end-module
"""
    )

    depth = sys.getrecursionlimit() + 200
    with pytest.raises(RecursionError):
        run_export(checked, "@app.run", RuntimeHostBindings({}), depth)


def test_runtime_quote_mediated_recursion_remains_unoptimized() -> None:
    checked = analyze_program(
        """module @app
  : loop-via-quote { n:Int -- out:Int }
    n 0 = if
      0
    else
      n 1 -
      :[ | x:Int -- y:Int | x loop-via-quote ;]
      call
    end
  ;
  : run { n:Int -- out:Int }
    n loop-via-quote
  ;
  export : run
end-module
"""
    )

    depth = sys.getrecursionlimit() + 200
    with pytest.raises(RecursionError):
        run_export(checked, "@app.run", RuntimeHostBindings({}), depth)


def test_runtime_self_call_followed_by_propagate_remains_unoptimized() -> None:
    checked = analyze_program(
        """module @app
  : loop-result { n:Int -- r:Result<Int,MapError> }
    n 0 = if
      0 Ok!
    else
      n 1 - loop-result ? Ok!
    end
  ;
  : run { n:Int -- r:Result<Int,MapError> }
    n loop-result
  ;
  export : run
end-module
"""
    )

    depth = sys.getrecursionlimit() + 200
    with pytest.raises(RecursionError):
        run_export(checked, "@app.run", RuntimeHostBindings({}), depth)


def test_runtime_multiple_host_words() -> None:
    log_signature = signature_from_source("""module @app
  : hostlog { msg:String -- } ;
end-module
""")
    random_signature = signature_from_source("""module @app
  : hostrandom { -- n:Int } ;
end-module
""")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.log", signature=log_signature, effect=HostEffect.PURE),
            HostWord(name="host.random-int", signature=random_signature, effect=HostEffect.PURE),
        ]
    )

    seen: list[str] = []
    checked = analyze_program(
        """module @app
  : process { msg:String -- n:Int }
    msg host.log
    host.random-int
  ;
  export : process
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings(
        {
            "host.log": lambda msg: seen.append(msg),
            "host.random-int": lambda: 42,
        }
    )
    result = run_export(checked, "@app.process", runtime, "hello")

    assert seen == ["hello"]
    assert result == 42


def test_runtime_scopes_with_same_nested_name_remain_distinct() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.log", signature=host_signature, effect=HostEffect.PURE)])

    seen: list[str] = []
    checked = analyze_program(
        """module @app
  : alpha { -- }
    : helper { -- }
      "alpha" host.log
    ;
    helper
  ;
  : beta { -- }
    : helper { -- }
      "beta" host.log
    ;
    helper
  ;
  export : alpha
  export : beta
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)})
    run_export(checked, "@app.alpha", runtime)
    run_export(checked, "@app.beta", runtime)

    assert seen == ["alpha", "beta"]


def test_runtime_host_multi_output() -> None:
    host_signature = signature_from_source("""module @app
  : hostpair { -- a:Int b:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : pair { -- a:Int b:Int }
    host.pair
  ;
  export : pair
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.pair": lambda: (1, 2)})
    result = run_export(checked, "@app.pair", runtime)

    assert result == (1, 2)


def test_runtime_host_multi_output_wrong_tuple_size() -> None:
    host_signature = signature_from_source("""module @app
  : hostpair { -- a:Int b:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : pair { -- a:Int b:Int }
    host.pair
  ;
  export : pair
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.pair": lambda: (1,)})
    with pytest.raises(RuntimeError, match="wrong runtime signature"):
        run_export(checked, "@app.pair", runtime)


def test_runtime_host_multi_output_wrong_element_type() -> None:
    host_signature = signature_from_source("""module @app
  : hostpair { -- a:Int b:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.pair", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : pair { -- a:Int b:Int }
    host.pair
  ;
  export : pair
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings({"host.pair": lambda: (1, "bad")})
    with pytest.raises(RuntimeError, match="host output 'b'"):
        run_export(checked, "@app.pair", runtime)


def test_runtime_unit_input_and_output_accept_unit_sentinel() -> None:
    checked = analyze_program(
        """module @app
  : echo-unit { u:Unit -- v:Unit }
    u
  ;
  export : echo-unit
end-module
"""
    )

    result = run_export(checked, "@app.echo-unit", RuntimeHostBindings({}), UNIT)
    assert result is UNIT


def test_runtime_unit_input_rejects_non_unit_values() -> None:
    checked = analyze_program(
        """module @app
  : echo-unit { u:Unit -- v:Unit }
    u
  ;
  export : echo-unit
end-module
"""
    )

    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "@app.echo-unit", RuntimeHostBindings({}), 123)
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "@app.echo-unit", RuntimeHostBindings({}), "abc")
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "@app.echo-unit", RuntimeHostBindings({}), True)
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "@app.echo-unit", RuntimeHostBindings({}), None)


def test_runtime_zero_output_and_unit_output_are_distinct() -> None:
    checked = analyze_program(
        """module @app
  : no-output { -- }
  ;
  : unit-output { -- u:Unit }
    host.produce-unit
  ;
  export : no-output
  export : unit-output
end-module
""",
        host_contract=host_contract_from_words(
            [HostWord(name="host.produce-unit", signature=signature_from_source("""module @app
  : hostproduce { -- u:Unit } ;
end-module
"""), effect=HostEffect.PURE)]
        ),
    )

    runtime = RuntimeHostBindings({"host.produce-unit": lambda: UNIT})
    assert run_export(checked, "@app.no-output", runtime) is None
    assert run_export(checked, "@app.unit-output", runtime) is UNIT


def test_runtime_host_unit_boundaries() -> None:
    host_in_signature = signature_from_source("""module @app
  : hostconsume { u:Unit -- n:Int } ;
end-module
""")
    host_out_signature = signature_from_source("""module @app
  : hostproduce { -- u:Unit } ;
end-module
""")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.consume-unit", signature=host_in_signature, effect=HostEffect.PURE),
            HostWord(name="host.produce-unit", signature=host_out_signature, effect=HostEffect.PURE),
        ]
    )

    checked = analyze_program(
        """module @app
  : consume { -- n:Int }
    host.produce-unit
    host.consume-unit
  ;
  : direct-consume { u:Unit -- n:Int }
    u host.consume-unit
  ;
  export : consume
  export : direct-consume
end-module
""",
        host_contract=host_contract,
    )

    runtime_ok = RuntimeHostBindings(
        {
            "host.produce-unit": lambda: UNIT,
            "host.consume-unit": lambda u: 7,
        }
    )
    assert run_export(checked, "@app.consume", runtime_ok) == 7
    assert run_export(checked, "@app.direct-consume", runtime_ok, UNIT) == 7

    runtime_bad_output = RuntimeHostBindings(
        {
            "host.produce-unit": lambda: None,
            "host.consume-unit": lambda u: 7,
        }
    )
    with pytest.raises(RuntimeError, match="host output 'u': expected Unit"):
        run_export(checked, "@app.consume", runtime_bad_output)

    runtime_bad_output_2 = RuntimeHostBindings(
        {
            "host.produce-unit": lambda: 123,
            "host.consume-unit": lambda u: 7,
        }
    )
    with pytest.raises(RuntimeError, match="host output 'u': expected Unit"):
        run_export(checked, "@app.consume", runtime_bad_output_2)

    runtime_bad_input = RuntimeHostBindings(
        {
            "host.produce-unit": lambda: None,
            "host.consume-unit": lambda u: 7,
        }
    )
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "@app.direct-consume", runtime_bad_input, 123)
    with pytest.raises(RuntimeError, match="input 'u': expected Unit"):
        run_export(checked, "@app.direct-consume", runtime_bad_input, None)


def test_runtime_accepts_valid_nested_list_result_input() -> None:
    checked = analyze_program(
        """module @app
  : echo { xs:List<Result<Int,Bool>> -- ys:List<Result<Int,Bool>> }
    xs
  ;
  export : echo
end-module
"""
    )

    payload = (Ok(1), Err(True), Ok(2))
    assert run_export(checked, "@app.echo", RuntimeHostBindings({}), payload) == payload


def test_runtime_rejects_invalid_nested_list_result_input() -> None:
    checked = analyze_program(
        """module @app
  : echo { xs:List<Result<Int,Bool>> -- ys:List<Result<Int,Bool>> }
    xs
  ;
  export : echo
end-module
"""
    )

    with pytest.raises(RuntimeError, match="input 'xs': expected List<Result<Int, Bool>>"):
        run_export(checked, "@app.echo", RuntimeHostBindings({}), (Ok("x"), Err(True)))


def test_runtime_accepts_valid_nested_map_result_host_output() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,Result<Int,Bool>> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- m:Map<String,Result<Int,Bool>> }
    host.map
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    value = {"a": Ok(1), "b": Err(True)}
    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: value})) == value


def test_runtime_rejects_invalid_nested_map_result_host_output() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,Result<Int,Bool>> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- m:Map<String,Result<Int,Bool>> }
    host.map
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    with pytest.raises(RuntimeError, match="host output 'm': expected Map<String, Result<Int, Bool>>"):
        run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {"a": "wrong"}}))


def test_runtime_accepts_valid_nested_result_host_output() -> None:
    host_signature = signature_from_source("""module @app
  : hostresult { -- r:Result<Int,Bool> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.result", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,Bool> }
    host.result
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.result": lambda: Ok(1)})) == Ok(1)
    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.result": lambda: Err(True)})) == Err(True)


def test_runtime_rejects_invalid_nested_result_host_output() -> None:
    host_signature = signature_from_source("""module @app
  : hostresult { -- r:Result<Int,Bool> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.result", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,Bool> }
    host.result
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    with pytest.raises(RuntimeError, match="host output 'r': expected Result<Int, Bool>"):
        run_export(checked, "@app.run", RuntimeHostBindings({"host.result": lambda: Ok("x")}))
    with pytest.raises(RuntimeError, match="host output 'r': expected Result<Int, Bool>"):
        run_export(checked, "@app.run", RuntimeHostBindings({"host.result": lambda: Err(123)}))


def test_runtime_deep_nested_recursive_validation() -> None:
    host_signature = signature_from_source("""module @app
  : hostdeep { -- xs:List<Result<Map<String,List<Int>>,Bool>> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.deep", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- xs:List<Result<Map<String,List<Int>>,Bool>> }
    host.deep
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    good = (Ok({"a": (1, 2)}), Err(True))
    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.deep": lambda: good})) == good

    bad = (Ok({"a": (1, "x")}), Err(True))
    with pytest.raises(RuntimeError, match="host output 'xs': expected List<Result<Map<String, List<Int>>, Bool>>"):
        run_export(checked, "@app.run", RuntimeHostBindings({"host.deep": lambda: bad}))


def test_runtime_if_true_executes_then_branch() -> None:
    checked = analyze_program(
        """module @app
  : run { -- }
    true
    if
      "yes" host.log
    else
      "no" host.log
    end
  ;
  export : run
end-module
""",
        host_contract=host_contract_from_words(
            [HostWord(name="host.log", signature=signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
"""), effect=HostEffect.PURE)]
        ),
    )

    seen: list[str] = []
    run_export(checked, "@app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}))
    assert seen == ["yes"]


def test_runtime_nested_if_in_nested_word() -> None:
    checked = analyze_program(
        """module @app
  : inner { flag:Bool -- n:Int }
    flag if
      1
    else
      0
    end
  ;
  : run { -- n:Int }
    true
    inner
  ;
  export : run
end-module
"""
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({}))
    assert result == 1


def test_runtime_case_bool_true_false_branches() -> None:
    checked = analyze_program(
        """module @app
  : choose { flag:Bool -- n:Int }
    flag
    case
      true => 1
      false => 2
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), True) == 1
    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), False) == 2


def test_runtime_case_produces_stack_output() -> None:
    checked = analyze_program(
        """module @app
  : choose { flag:Bool -- n:Int }
    flag
    case
      true => 1
      false => 2
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), True) == 1
    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), False) == 2


def test_runtime_case_can_call_nicole_word() -> None:
    host_contract = host_contract_from_words(
        [HostWord(name="host.log", signature=signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
"""), effect=HostEffect.PURE)]
    )
    checked = analyze_program(
        """module @app
  : log-yes { -- }
    "yes" host.log
  ;
  : run { flag:Bool -- }
    flag
    case
      true => log-yes
      false => log-yes
    end
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    seen: list[str] = []
    run_export(checked, "@app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}), True)

    assert seen == ["yes"]


def test_runtime_nested_case() -> None:
    checked = analyze_program(
        """module @app
  : run { flag:Bool -- n:Int }
    flag
    case
      true =>
        false
        case
          true => 1
          false => 2
        end
      false => 3
    end
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({}), True) == 2
    assert run_export(checked, "@app.run", RuntimeHostBindings({}), False) == 3


def test_runtime_case_result_ok_binding() -> None:
    checked = analyze_program(
        """module @app
  : unwrap { r:Result<Int,MapError> -- n:Int }
    r
    case
      Ok(v) => v
      Err(MissingKey) => 0
    end
  ;
  export : unwrap
end-module
"""
    )

    assert run_export(checked, "@app.unwrap", RuntimeHostBindings({}), Ok(42)) == 42


def test_runtime_case_result_err_missing_key_variant() -> None:
    checked = analyze_program(
        """module @app
  : unwrap { r:Result<Int,MapError> -- n:Int }
    r
    case
      Ok(v) => v
      Err(MissingKey) => 0
    end
  ;
  export : unwrap
end-module
"""
    )

    assert run_export(checked, "@app.unwrap", RuntimeHostBindings({}), Err("MissingKey")) == 0


def test_runtime_case_result_err_out_of_bounds_variant() -> None:
    checked = analyze_program(
        """module @app
  : unwrap { r:Result<Int,ListError> -- n:Int }
    r
    case
      Ok(v) => v
      Err(OutOfBounds) => 0
    end
  ;
  export : unwrap
end-module
"""
    )

    assert run_export(checked, "@app.unwrap", RuntimeHostBindings({}), Err("OutOfBounds")) == 0


def test_runtime_case_result_other_error_no_match() -> None:
    checked = analyze_program(
        """module @app
  : unwrap { r:Result<Int,MapError> -- n:Int }
    r
    case
      Err(MissingKey) => 0
      Ok(v) => v
    end
  ;
  export : unwrap
end-module
"""
    )

    with pytest.raises(RuntimeError, match="input 'r': expected Result<Int, MapError>"):
        run_export(checked, "@app.unwrap", RuntimeHostBindings({}), Err("Other"))


def test_runtime_propagate_ok_continues_execution() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,MapError> }
    map.empty:Map<String,Int>
    "k" 41 map.set
    "k" map.get
    ?
    1 +
    Ok!
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Ok(42)


def test_runtime_propagate_err_returns_immediately() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,MapError> }
    map.empty:Map<String,Int>
    "missing" map.get
    ?
    0 +
    Ok!
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("MissingKey")


def test_runtime_propagate_is_frame_local_inside_quotation() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    map.empty:Map<String,Int>
    :[ | m:Map<String,Int> -- r:Result<Int,MapError> |
      m "missing" map.get
      ?
      1 +
      Ok!
    ;]
    call
    9 result.unwrap-or
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 9


def test_runtime_propagate_multiple_in_one_frame() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,MapError> }
    map.empty:Map<String,Int>
    "a" 1 map.set
    "a" map.get
    ?
    drop
    map.empty:Map<String,Int>
    "missing" map.get
    ?
    drop
    100 Ok!
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("MissingKey")


def test_runtime_case_branch_local_binding_does_not_escape_branch_scope() -> None:
    host_signature = signature_from_source("""module @app
  : hostfetch { -- r:Result<Int,MapError> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.fetch", signature=host_signature, effect=HostEffect.PURE)])

    with pytest.raises(ResolutionError):
        analyze_program(
            """module @app
  : run { -- n:Int }
    host.fetch
    case
      Ok(v) => v
      Err(MissingKey) => 0
    end
    v
  ;
  export : run
end-module
""",
            host_contract=host_contract,
        )


def test_runtime_case_err_binding_returns_runtime_error_value() -> None:
    fetch_signature = signature_from_source("""module @app
  : hostfetch { -- r:Result<Int,MapError> } ;
end-module
""")
    fallback_signature = signature_from_source("""module @app
  : hostfallback { -- e:MapError } ;
end-module
""")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.fetch", signature=fetch_signature, effect=HostEffect.PURE),
            HostWord(name="host.fallback-error", signature=fallback_signature, effect=HostEffect.PURE),
        ]
    )
    checked = analyze_program(
        """module @app
  : run { -- e:MapError }
    host.fetch
    case
      Ok(v) => host.fallback-error
      Err(e) => e
    end
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    runtime = RuntimeHostBindings(
        {
            "host.fetch": lambda: Err("MissingKey"),
            "host.fallback-error": lambda: "MissingKey",
        }
    )
    assert run_export(checked, "@app.run", runtime) == "MissingKey"


def test_runtime_case_first_matching_branch_wins() -> None:
    checked = analyze_program(
        """module @app
  : choose { b:Bool -- n:Int }
    b
    case
      _ => 10
      true => 1
      false => 2
    end
  ;
  export : choose
end-module
"""
    )

    # Wildcard comes first in source/AST order, so it must win.
    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), True) == 10


def test_runtime_case_guard_true_selects_branch() -> None:
    checked = analyze_program(
        """module @app
  : choose { n:Int -- out:Int }
    n
    case
      _ when true => 1
      _ => 2
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), 42) == 1


def test_runtime_case_guard_false_falls_through() -> None:
    checked = analyze_program(
        """module @app
  : choose { n:Int -- out:Int }
    n
    case
      _ when false => 1
      _ => 2
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), 42) == 2


def test_runtime_case_pattern_mismatch_does_not_evaluate_guard() -> None:
    checked = analyze_program(
        """module @app
  : choose { b:Bool -- out:Int }
    b
    case
      true when true => 1
      true => 3
      false => 2
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), False) == 2


def test_runtime_case_guard_can_use_pattern_binding() -> None:
    checked = analyze_program(
        """module @app
  : choose { r:Result<Int,MapError> -- out:Int }
    r
    case
      Ok(v) when v 0 > => 1
      Ok(v) => 0
      Err(MissingKey) => 99
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), Ok(4)) == 1
    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), Ok(-4)) == 0


def test_runtime_case_first_eligible_guarded_branch_wins() -> None:
    checked = analyze_program(
        """module @app
  : choose { n:Int -- out:Int }
    n
    case
      _ when true => 10
      _ when true => 20
      _ => 30
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), 7) == 10


def test_runtime_case_unguarded_branch_still_works_with_guarded_branch_present() -> None:
    checked = analyze_program(
        """module @app
  : choose { b:Bool -- out:Int }
    b
    case
      true when false => 1
      true => 2
      false => 3
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), True) == 2
    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), False) == 3


def test_runtime_case_wildcard_guard_is_conditional() -> None:
    checked = analyze_program(
        """module @app
  : choose { n:Int -- out:Int }
    n
    case
      _ when n 0 > => 1
      _ => 2
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), 9) == 1
    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), -9) == 2


def test_runtime_case_wildcard_guard_false_falls_through_to_unguarded_wildcard() -> None:
    checked = analyze_program(
        """module @app
  : choose { n:Int -- out:Int }
    n
    case
      _ when false => 1
      _ => 2
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), 0) == 2


def test_runtime_case_no_branch_match_behavior_unchanged() -> None:
    checked = analyze_program(
        """module @app
  : choose { n:Int -- out:Int }
    n
    case
      0 when true => 1
    end
  ;
  export : choose
end-module
"""
    )

    with pytest.raises(RuntimeError, match="runtime case match failure"):
        run_export(checked, "@app.choose", RuntimeHostBindings({}), 1)


def test_runtime_case_guard_does_not_leak_stack_values() -> None:
    checked = analyze_program(
        """module @app
  : choose { n:Int -- out:Int }
    n
    case
      _ when n 0 > => 100
      _ => 200
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), 1) == 100
    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), -1) == 200


def test_runtime_quote_literal_returns_runtime_quote_value() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            """module @app
  : run { -- q:Quote<{ | -- n:Int }> }
    :[ | -- n:Int | 1 ;]
  ;
  export : run
end-module
"""
        )


def test_runtime_call_returns_literal() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    :[ | -- n:Int | 7 ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 7


def test_runtime_call_executes_arithmetic() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    :[ | -- n:Int | 1 2 + ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 3


def test_runtime_call_with_one_input() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    5
    :[ | x:Int -- y:Int | x 1 + ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 6


def test_runtime_call_with_multiple_inputs() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    1 2
    :[ | x:Int y:Int -- z:Int | x y + ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 3


def test_runtime_call_non_commutative_input_order() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    7 3
    :[ | x:Int y:Int -- z:Int | x y - ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 4


def test_runtime_call_with_capture_end_to_end() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    5
    10
    :[ a:Int | x:Int -- y:Int | a x + ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 15


def test_runtime_call_capture_and_input_interaction() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    4
    3
    :[ k:Int | x:Int -- y:Int | x k * ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 12


def test_runtime_call_multiple_output_order() -> None:
    checked = analyze_program(
        """module @app
  : run { -- first:Int second:Int }
    1 2
    :[ | x:Int y:Int -- first:Int second:Int | y x ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == (2, 1)


def test_runtime_call_can_call_nicole_word() -> None:
    checked = analyze_program(
        """module @app
  : plus-one { x:Int -- y:Int }
    x 1 +
  ;
  : run { -- n:Int }
    5
    :[ | x:Int -- y:Int | x plus-one ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 6


def test_runtime_call_can_call_host_word() -> None:
    host_signature = signature_from_source("""module @app
  : hostsig { n:Int -- out:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.inc", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    5
    :[ | x:Int -- y:Int | x host.inc ;]
    call
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.inc": lambda n: n + 1})) == 6


def test_runtime_call_on_non_quote_is_controlled_error() -> None:
    stack = RuntimeStack()
    stack.push(123)

    with pytest.raises(RuntimeError, match="call expects runtime quotation"):
        _execute_call({}, stack, {}, RuntimeHostBindings({}))


def test_runtime_nested_quotes_are_not_auto_executed() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            """module @app
  : run { -- q:Quote<{ | -- n:Int }> }
    :[ | -- q:Quote<{ | -- n:Int }> | :[ | -- n:Int | 1 ;] ;]
    call
  ;
  export : run
end-module
"""
        )


def test_runtime_nested_quote_executes_only_with_explicit_second_call() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    :[ | -- q:Quote<{ | -- n:Int }> | :[ | -- n:Int | 1 ;] ;]
    call
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 1


def test_runtime_typed_empty_list_returns_empty_tuple() -> None:
    checked = analyze_program(
        """module @app
  : run { -- xs:List<Int> }
    []:List<Int>
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == ()


def test_runtime_list_literal_returns_tuple_in_source_order() -> None:
    checked = analyze_program(
        """module @app
  : run { -- xs:List<Int> }
    [1, 2, 3]
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == (1, 2, 3)


def test_runtime_list_literal_elements_evaluate_left_to_right() -> None:
    host_signature = signature_from_source("""module @app
  : hostnext { -- n:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.next", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- xs:List<Int> }
    [host.next, host.next, host.next]
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    counter = {"value": 0}

    def next_value() -> int:
        counter["value"] += 1
        return counter["value"]

    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.next": next_value})) == (1, 2, 3)


def test_runtime_nested_list_literal_returns_nested_tuple() -> None:
    checked = analyze_program(
        """module @app
  : run { -- xs:List<List<Int>> }
    [[1, 2], [3, 4]]
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == ((1, 2), (3, 4))


def test_runtime_quotation_inside_list_is_preserved_not_executed() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            """module @app
  : run { -- xs:List<Quote<{ | -- n:Int }>> }
    [:[ | -- n:Int | 1 ;]]
  ;
  export : run
end-module
"""
        )


def test_runtime_host_result_can_be_packed_into_list_literal() -> None:
    host_signature = signature_from_source("""module @app
  : hostnum { -- n:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.num", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- xs:List<Int> }
    [host.num, 2]
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.num": lambda: 1})) == (1, 2)


def test_runtime_list_literal_error_in_element_aborts_construction() -> None:
    host_signature = signature_from_source("""module @app
  : hostfail { -- n:Int } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.fail", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- xs:List<Int> }
    [1, host.fail, 3]
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    def fail() -> int:
        raise ValueError("boom")

    with pytest.raises(RuntimeError, match="runtime host error: host.fail"):
        run_export(checked, "@app.run", RuntimeHostBindings({"host.fail": fail}))


def test_runtime_list_len_typed_empty_list_is_zero() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    []:List<Int>
    list.len
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 0


def test_runtime_list_len_non_empty_list_literal() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    [1, 2, 3]
    list.len
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 3


def test_runtime_list_len_nested_list_counts_top_level_only() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    [[1, 2], [3, 4], [5]]
    list.len
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 3


def test_runtime_list_len_quotation_inside_list_counts_as_one() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    [:[ | -- n:Int | 1 ;], :[ | -- n:Int | 2 ;]]
    list.len
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 2


def test_runtime_list_len_malformed_runtime_value_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    []:List<Int>
    list.len
  ;
  export : run
end-module
"""
    )
    list_len_node = checked.program.words[0].body.items[1]
    stack = RuntimeStack()
    stack.push("not-a-list")

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.len input: expected List"):
        _execute_identifier(list_len_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_is_empty_executes() -> None:
    checked = analyze_program(
        """module @app
  : empty { -- b:Bool }
    []:List<Int> list.is-empty
  ;
  : non-empty { -- b:Bool }
    [1] list.is-empty
  ;
  export : empty
  export : non-empty
end-module
"""
    )

    assert run_export(checked, "@app.empty", RuntimeHostBindings({})) is True
    assert run_export(checked, "@app.non-empty", RuntimeHostBindings({})) is False


def test_runtime_list_first_and_last_execute() -> None:
    checked = analyze_program(
        """module @app
  : first { -- r:Result<Int,ListError> }
    [10, 20, 30] list.first
  ;
  : last { -- r:Result<Int,ListError> }
    [10, 20, 30] list.last
  ;
  export : first
  export : last
end-module
"""
    )

    assert run_export(checked, "@app.first", RuntimeHostBindings({})) == Ok(10)
    assert run_export(checked, "@app.last", RuntimeHostBindings({})) == Ok(30)


def test_runtime_list_first_and_last_empty_return_out_of_bounds_error() -> None:
    checked = analyze_program(
        """module @app
  : first-empty { -- r:Result<Int,ListError> }
    []:List<Int> list.first
  ;
  : last-empty { -- r:Result<Int,ListError> }
    []:List<Int> list.last
  ;
  export : first-empty
  export : last-empty
end-module
"""
    )

    assert run_export(checked, "@app.first-empty", RuntimeHostBindings({})) == Err("OutOfBounds")
    assert run_export(checked, "@app.last-empty", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_append_and_reverse_execute() -> None:
    checked = analyze_program(
        """module @app
  : append { -- xs:List<Int> }
    [1, 2] 3 list.append
  ;
  : reverse { -- xs:List<Int> }
    [1, 2, 3] list.reverse
  ;
  export : append
  export : reverse
end-module
"""
    )

    assert run_export(checked, "@app.append", RuntimeHostBindings({})) == (1, 2, 3)
    assert run_export(checked, "@app.reverse", RuntimeHostBindings({})) == (3, 2, 1)


def test_runtime_list_push_is_not_available_in_v1_surface() -> None:
    with pytest.raises(ResolutionError, match="unresolved name"):
        analyze_program(
            """module @app
  : run { -- xs:List<Int> }
    []:List<Int>
    10
    list.push
  ;
  export : run
end-module
"""
        )


def test_runtime_list_set_valid_replacement_returns_ok() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [10, 20, 30]
    0
    99
    list.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Ok((99, 20, 30))


def test_runtime_list_set_replacement_in_middle_position() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [10, 20, 30]
    1
    99
    list.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Ok((10, 99, 30))


def test_runtime_list_set_replacement_in_last_position() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [10, 20, 30]
    2
    99
    list.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Ok((10, 20, 99))


def test_runtime_list_set_empty_list_returns_out_of_bounds() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    []:List<Int>
    0
    1
    list.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_set_negative_index_returns_out_of_bounds() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [10, 20, 30]
    0 1 -
    99
    list.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_set_index_equal_to_length_returns_out_of_bounds() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [10, 20, 30]
    3
    99
    list.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_set_index_greater_than_length_returns_out_of_bounds() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [10, 20, 30]
    4
    99
    list.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_set_nested_tuple_is_preserved() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<List<Int>>,ListError> }
    [[1], [2], [3]]
    1
    [9]
    list.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Ok(((1,), (9,), (3,)))


def test_runtime_list_set_runtime_quote_is_preserved() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            """module @app
  : run { -- r:Result<List<Quote<{ | -- n:Int }>>,ListError> }
    [:[ | -- n:Int | 1 ;], :[ | -- n:Int | 2 ;]]
    1
    :[ | -- n:Int | 3 ;]
    list.set
  ;
  export : run
end-module
"""
        )


def test_runtime_list_set_preserves_stored_ok_value() -> None:
    stored_ok = Ok(123)
    host_signature = signature_from_source("""module @app
  : hostok { -- r:Result<Int,MapError> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.ok", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Result<Int,MapError>>,ListError> }
    [host.ok]
    0
    host.ok
    list.set
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.ok": lambda: stored_ok}))
    assert isinstance(result, Ok)
    assert result.value == (stored_ok,)
    assert result.value[0] is stored_ok


def test_runtime_list_set_preserves_stored_err_value() -> None:
    stored_err = Err("MissingKey")
    host_signature = signature_from_source("""module @app
  : hosterr { -- r:Result<Int,MapError> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.err", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Result<Int,MapError>>,ListError> }
    [host.err]
    0
    host.err
    list.set
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.err": lambda: stored_err}))
    assert isinstance(result, Ok)
    assert result.value == (stored_err,)
    assert result.value[0] is stored_err


def test_runtime_list_set_returns_new_tuple_value() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [1, 2, 3]
    1
    9
    list.set
  ;
  export : run
end-module
"""
    )
    list_set_node = checked.program.words[0].body.items[3]
    original = (1, 2, 3)
    stack = RuntimeStack()
    stack.push(original)
    stack.push(1)
    stack.push(9)

    _execute_identifier(list_set_node, {}, stack, {}, RuntimeHostBindings({}))
    result = stack.pop()
    assert isinstance(result, Ok)
    assert result.value == (1, 9, 3)
    assert result.value is not original


def test_runtime_list_set_malformed_runtime_list_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [1, 2, 3]
    1
    9
    list.set
  ;
  export : run
end-module
"""
    )
    list_set_node = checked.program.words[0].body.items[3]
    stack = RuntimeStack()
    stack.push("not-a-list")
    stack.push(1)
    stack.push(9)

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.set list: expected List"):
        _execute_identifier(list_set_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_set_malformed_runtime_index_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [1, 2, 3]
    1
    9
    list.set
  ;
  export : run
end-module
"""
    )
    list_set_node = checked.program.words[0].body.items[3]
    stack = RuntimeStack()
    stack.push((1, 2, 3))
    stack.push("not-an-int")
    stack.push(9)

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.set index: expected Int"):
        _execute_identifier(list_set_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_get_valid_index_zero_returns_ok() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    [10, 20, 30]
    0
    list.get
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Ok(10)


def test_runtime_list_get_valid_middle_index_returns_ok() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    [10, 20, 30]
    1
    list.get
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Ok(20)


def test_runtime_list_get_valid_last_index_returns_ok() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    [10, 20, 30]
    2
    list.get
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Ok(30)


def test_runtime_list_get_empty_list_access_returns_out_of_bounds() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    []:List<Int>
    0
    list.get
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_get_index_equal_to_length_returns_out_of_bounds() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    [10, 20, 30]
    3
    list.get
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_get_index_greater_than_length_returns_out_of_bounds() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    [10, 20, 30]
    4
    list.get
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_get_negative_index_returns_out_of_bounds() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    [10, 20, 30]
    0 1 -
    list.get
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("OutOfBounds")


def test_runtime_list_get_nested_tuple_returned_unchanged() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [[1, 2], [3, 4]]
    0
    list.get
  ;
  export : run
end-module
"""
    )
    list_get_node = checked.program.words[0].body.items[2]
    inner = (1, 2)
    stack = RuntimeStack()
    stack.push((inner, (3, 4)))
    stack.push(0)

    _execute_identifier(list_get_node, {}, stack, {}, RuntimeHostBindings({}))
    result = stack.pop()
    assert isinstance(result, Ok)
    assert result.value is inner


def test_runtime_list_get_runtime_quote_returned_unchanged() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            """module @app
  : run { -- q:Quote<{ | -- n:Int }> }
    :[ | -- n:Int | 1 ;]
  ;
  export : run
end-module
"""
        )


def test_runtime_list_get_malformed_index_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    [10, 20, 30]
    0
    list.get
  ;
  export : run
end-module
"""
    )
    list_get_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push((10, 20, 30))
    stack.push("not-an-int")

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.get index: expected Int"):
        _execute_identifier(list_get_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_get_malformed_list_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,ListError> }
    [10, 20, 30]
    0
    list.get
  ;
  export : run
end-module
"""
    )
    list_get_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push("not-a-list")
    stack.push(0)

    with pytest.raises(RuntimeError, match="wrong runtime signature for list\\.get list: expected List"):
        _execute_identifier(list_get_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_list_get_preserves_stored_ok_value() -> None:
    stored_ok = Ok(123)
    host_signature = signature_from_source("""module @app
  : hostok { -- r:Result<Int,MapError> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.ok", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Result<Int,MapError>,ListError> }
    [host.ok]
    0
    list.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.ok": lambda: stored_ok}))
    assert isinstance(result, Ok)
    assert result.value is stored_ok
    assert result.value == stored_ok


def test_runtime_list_get_preserves_stored_err_value() -> None:
    stored_err = Err("MissingKey")
    host_signature = signature_from_source("""module @app
  : hosterr { -- r:Result<Int,MapError> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.err", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Result<Int,MapError>,ListError> }
    [host.err]
    0
    list.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.err": lambda: stored_err}))
    assert isinstance(result, Ok)
    assert result.value is stored_err
    assert result.value == stored_err


def test_runtime_list_get_preserves_stored_tuple_identity() -> None:
    stored_tuple = (1, 2)
    host_signature = signature_from_source("""module @app
  : hosttuple { -- xs:List<Int> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.tuple", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,ListError> }
    [host.tuple]
    0
    list.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.tuple": lambda: stored_tuple}))
    assert isinstance(result, Ok)
    assert result.value is stored_tuple
    assert result.value == stored_tuple


def test_runtime_map_empty_returns_empty_dict() -> None:
    checked = analyze_program(
        """module @app
  : run { -- m:Map<String,Int> }
    map.empty:Map<String,Int>
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == {}


def test_runtime_map_get_int_key_returns_ok() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<Int,String> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<String,MapError> }
    host.map
    1
    map.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {1: "one"}}))
    assert result == Ok("one")


def test_runtime_map_get_string_key_returns_ok() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,Int> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,MapError> }
    host.map
    "hello"
    map.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {"hello": 7}}))
    assert result == Ok(7)


def test_runtime_map_get_bool_key_returns_ok() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<Bool,Int> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,MapError> }
    host.map
    true
    map.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {True: 7}}))
    assert result == Ok(7)


def test_runtime_map_get_missing_key_returns_missing_key() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,MapError> }
    map.empty:Map<String,Int>
    "missing"
    map.get
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("MissingKey")


def test_runtime_map_get_nested_tuple_is_preserved() -> None:
    stored_tuple = (1, 2)
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,List<Int>> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,MapError> }
    host.map
    "pair"
    map.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {"pair": stored_tuple}}))
    assert isinstance(result, Ok)
    assert result.value is stored_tuple
    assert result.value == stored_tuple


def test_runtime_map_get_runtime_quote_is_preserved() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,Quote<{ | -- n:Int }>> } ;
end-module
""")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])


def test_runtime_map_get_stored_ok_and_err_values_are_preserved() -> None:
    stored_ok = Ok(123)
    stored_err = Err("MissingKey")
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,Result<Int,MapError>> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Result<Int,MapError>,MapError> }
    host.map
    "ok"
    map.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result_ok = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {"ok": stored_ok, "err": stored_err}}))
    assert isinstance(result_ok, Ok)
    assert result_ok.value is stored_ok
    assert result_ok.value == stored_ok

    checked_err = analyze_program(
        """module @app
  : run { -- r:Result<Result<Int,MapError>,MapError> }
    host.map
    "err"
    map.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )
    result_err = run_export(checked_err, "@app.run", RuntimeHostBindings({"host.map": lambda: {"ok": stored_ok, "err": stored_err}}))
    assert isinstance(result_err, Ok)
    assert result_err.value is stored_err
    assert result_err.value == stored_err


def test_runtime_map_get_unsupported_list_key_raises_runtime_error() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            """module @app
  : run { -- r:Result<Int,MapError> }
    map.empty:Map<List<Int>,Int>
    [1]
    map.get
  ;
  export : run
end-module
"""
        )


def test_runtime_map_get_unsupported_result_key_raises_runtime_error() -> None:
    host_signature = signature_from_source("""module @app
  : hostkey { -- k:Result<Int,MapError> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.key", signature=host_signature, effect=HostEffect.PURE)])
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            """module @app
  : run { -- r:Result<Int,MapError> }
    map.empty:Map<Result<Int,MapError>,Int>
    host.key
    map.get
  ;
  export : run
end-module
""",
            host_contract=host_contract,
        )


def test_runtime_map_contains_existing_key_returns_true() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,Int> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- b:Bool }
    host.map
    "hello"
    map.contains
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {"hello": 7}}))
    assert result is True


def test_runtime_map_contains_missing_key_returns_false() -> None:
    checked = analyze_program(
        """module @app
  : run { -- b:Bool }
    map.empty:Map<String,Int>
    "missing"
    map.contains
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) is False


def test_runtime_map_contains_bool_key_returns_true() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<Bool,Int> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- b:Bool }
    host.map
    true
    map.contains
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {True: 7}}))
    assert result is True


def test_runtime_map_contains_unsupported_quote_key_raises_runtime_error() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            """module @app
  : run { -- b:Bool }
    map.empty:Map<Quote<{ | -- n:Int }>,Int>
    :[ | -- n:Int | 1 ;]
    map.contains
  ;
  export : run
end-module
"""
        )


def test_runtime_map_get_malformed_runtime_map_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Int,MapError> }
    map.empty:Map<String,Int>
    "hello"
    map.get
  ;
  export : run
end-module
"""
    )
    map_get_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push(["not-a-map"])
    stack.push("hello")

    with pytest.raises(RuntimeError, match="wrong runtime signature for map\\.get map: expected Map"):
        _execute_identifier(map_get_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_map_contains_malformed_runtime_map_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- b:Bool }
    map.empty:Map<String,Int>
    "hello"
    map.contains
  ;
  export : run
end-module
"""
    )
    map_contains_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push(["not-a-map"])
    stack.push("hello")

    with pytest.raises(RuntimeError, match="wrong runtime signature for map\\.contains map: expected Map"):
        _execute_identifier(map_contains_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_map_set_inserts_new_int_key() -> None:
    checked = analyze_program(
        """module @app
  : run { -- m:Map<Int,String> }
    map.empty:Map<Int,String>
    1
    "one"
    map.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == {1: "one"}


def test_runtime_map_set_updates_existing_int_key() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<Int,String> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- m:Map<Int,String> }
    host.map
    1
    "uno"
    map.set
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {1: "one"}})) == {1: "uno"}


def test_runtime_map_set_string_key() -> None:
    checked = analyze_program(
        """module @app
  : run { -- m:Map<String,Int> }
    map.empty:Map<String,Int>
    "hello"
    7
    map.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == {"hello": 7}


def test_runtime_map_set_bool_key() -> None:
    checked = analyze_program(
        """module @app
  : run { -- m:Map<Bool,Int> }
    map.empty:Map<Bool,Int>
    true
    7
    map.set
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == {True: 7}


def test_runtime_map_set_returns_new_dict_and_preserves_original() -> None:
    host_map = {1: "one"}
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<Int,String> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- m:Map<Int,String> }
    host.map
    2
    "two"
    map.set
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: host_map}))
    assert result == {1: "one", 2: "two"}
    assert result is not host_map
    assert host_map == {1: "one"}


def test_runtime_map_set_preserves_nested_tuple_value() -> None:
    stored_tuple = (1, 2)
    checked = analyze_program(
        """module @app
  : run { -- r:Result<List<Int>,MapError> }
    map.empty:Map<String,List<Int>>
    "pair"
    [1, 2]
    map.set
    "pair"
    map.get
  ;
  export : run
end-module
"""
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({}))
    assert result == Ok(stored_tuple)


def test_runtime_map_set_preserves_runtime_quote_value() -> None:
    host_signature = signature_from_source("""module @app
  : hostquote { -- q:Quote<{ | -- n:Int }> } ;
end-module
""")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.quote", signature=host_signature, effect=HostEffect.PURE)])


def test_runtime_map_set_preserves_stored_ok_and_err_values() -> None:
    stored_ok = Ok(123)
    stored_err = Err("MissingKey")
    ok_signature = signature_from_source("""module @app
  : hostok { -- r:Result<Int,MapError> } ;
end-module
""")
    err_signature = signature_from_source("""module @app
  : hosterr { -- r:Result<Int,MapError> } ;
end-module
""")
    host_contract = host_contract_from_words(
        [
            HostWord(name="host.ok", signature=ok_signature, effect=HostEffect.PURE),
            HostWord(name="host.err", signature=err_signature, effect=HostEffect.PURE),
        ]
    )

    checked_ok = analyze_program(
        """module @app
  : run { -- r:Result<Result<Int,MapError>,MapError> }
    map.empty:Map<String,Result<Int,MapError>>
    "ok"
    host.ok
    map.set
    "ok"
    map.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )
    result_ok = run_export(
        checked_ok,
            "@app.run",
        RuntimeHostBindings({"host.ok": lambda: stored_ok, "host.err": lambda: stored_err}),
    )
    assert isinstance(result_ok, Ok)
    assert result_ok.value is stored_ok

    checked_err = analyze_program(
        """module @app
  : run { -- r:Result<Result<Int,MapError>,MapError> }
    map.empty:Map<String,Result<Int,MapError>>
    "err"
    host.err
    map.set
    "err"
    map.get
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )
    result_err = run_export(
        checked_err,
            "@app.run",
        RuntimeHostBindings({"host.ok": lambda: stored_ok, "host.err": lambda: stored_err}),
    )
    assert isinstance(result_err, Ok)
    assert result_err.value is stored_err


def test_runtime_map_set_malformed_runtime_map_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- m:Map<String,Int> }
    map.empty:Map<String,Int>
    "hello"
    1
    map.set
  ;
  export : run
end-module
"""
    )
    map_set_node = checked.program.words[0].body.items[3]
    stack = RuntimeStack()
    stack.push(["not-a-map"])
    stack.push("hello")
    stack.push(1)

    with pytest.raises(RuntimeError, match="wrong runtime signature for map\\.set map: expected Map"):
        _execute_identifier(map_set_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_map_set_unsupported_key_type_raises_runtime_error() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            """module @app
  : run { -- m:Map<List<Int>,Int> }
    map.empty:Map<List<Int>,Int>
    [1]
    1
    map.set
  ;
  export : run
end-module
"""
        )


def test_runtime_map_remove_existing_key_returns_ok_new_dict() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<Int,String> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Map<Int,String>,MapError> }
    host.map
    1
    map.remove
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {1: "one", 2: "two"}})) == Ok({2: "two"})


def test_runtime_map_remove_missing_key_returns_missing_key() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Map<String,Int>,MapError> }
    map.empty:Map<String,Int>
    "missing"
    map.remove
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == Err("MissingKey")


def test_runtime_map_remove_returns_new_dict_and_preserves_original() -> None:
    host_map = {1: "one", 2: "two"}
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<Int,String> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Map<Int,String>,MapError> }
    host.map
    1
    map.remove
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: host_map}))
    assert result == Ok({2: "two"})
    assert isinstance(result, Ok)
    assert result.value is not host_map
    assert host_map == {1: "one", 2: "two"}


def test_runtime_map_remove_string_key() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,Int> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Map<String,Int>,MapError> }
    host.map
    "hello"
    map.remove
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {"hello": 7, "bye": 9}})) == Ok({"bye": 9})


def test_runtime_map_remove_bool_key() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<Bool,Int> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Map<Bool,Int>,MapError> }
    host.map
    true
    map.remove
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({"host.map": lambda: {True: 7, False: 9}})) == Ok({False: 9})


def test_runtime_map_remove_preserves_remaining_nested_values() -> None:
    stored_tuple = (1, 2)
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,List<Int>> } ;
end-module
""")
    host_contract = host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Map<String,List<Int>>,MapError> }
    host.map
    "drop"
    map.remove
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    result = run_export(
        checked,
        "@app.run",
        RuntimeHostBindings({"host.map": lambda: {"drop": (9,), "keep": stored_tuple}}),
    )
    assert isinstance(result, Ok)
    assert result.value == {"keep": stored_tuple}
    assert result.value["keep"] is stored_tuple


def test_runtime_map_remove_preserves_remaining_quote_values() -> None:
    host_signature = signature_from_source("""module @app
  : hostmap { -- m:Map<String,Quote<{ | -- n:Int }>> } ;
end-module
""")
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        host_contract_from_words([HostWord(name="host.map", signature=host_signature, effect=HostEffect.PURE)])


def test_runtime_map_remove_malformed_runtime_map_is_controlled_error() -> None:
    checked = analyze_program(
        """module @app
  : run { -- r:Result<Map<String,Int>,MapError> }
    map.empty:Map<String,Int>
    "hello"
    map.remove
  ;
  export : run
end-module
"""
    )
    map_remove_node = checked.program.words[0].body.items[2]
    stack = RuntimeStack()
    stack.push(["not-a-map"])
    stack.push("hello")

    with pytest.raises(RuntimeError, match="wrong runtime signature for map\\.remove map: expected Map"):
        _execute_identifier(map_remove_node, {}, stack, {}, RuntimeHostBindings({}))


def test_runtime_map_remove_unsupported_key_type_raises_runtime_error() -> None:
    with pytest.raises(CheckerError, match="Map<K,V> key type must be Int, String, or Bool in v1"):
        analyze_program(
            """module @app
  : run { -- r:Result<Map<List<Int>,Int>,MapError> }
    map.empty:Map<List<Int>,Int>
    [1]
    map.remove
  ;
  export : run
end-module
"""
        )


def test_runtime_list_map_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- ys:List<Int> }
    [1, 2]
    :[ | x:Int -- y:Int | x 1 + ;]
    list.map
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == (2, 3)


def test_runtime_list_map_inside_quote_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- ys:List<Int> }
    :[ | -- ys:List<Int> |
      [1, 2]
      :[ | x:Int -- y:Int | x 1 + ;]
      list.map
    ;]
    call
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == (2, 3)


def test_runtime_list_filter_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- ys:List<Int> }
    [1, 2, 3, 4]
    :[ | x:Int -- keep:Bool | true ;]
    list.filter
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == (1, 2, 3, 4)


def test_runtime_list_fold_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    [1, 2, 3]
    10
    :[ | acc:Int x:Int -- out:Int | acc x + ;]
    list.fold
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 16


def test_runtime_list_reduce_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    [2, 3, 4]
    :[ | a:Int b:Int -- c:Int | a b + ;]
    list.reduce
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 9


def test_runtime_list_reduce_empty_from_host_is_runtime_error() -> None:
    host_signature = signature_from_source("""module @app
  : hostlist { -- xs:List<Int> } ;
end-module
""")
    host_contract = host_contract_from_words(
        [HostWord(name="host.list", signature=host_signature, effect=HostEffect.PURE)]
    )
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    host.list
    :[ | a:Int b:Int -- c:Int | a b + ;]
    list.reduce
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    with pytest.raises(RuntimeError, match="list.reduce cannot be applied to empty list at runtime"):
        run_export(checked, "@app.run", RuntimeHostBindings({"host.list": lambda: ()}))


def test_runtime_list_map_with_nested_quote_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- ys:List<Int> }
    [1, 2]
    :[ | x:Int -- y:Int |
      x
      :[ | n:Int -- m:Int | n 10 + ;]
      call
    ;]
    list.map
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == (11, 12)


def test_runtime_result_is_ok_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- b:Bool }
    7 Ok!
    result.is-ok
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) is True


def test_runtime_result_is_err_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- b:Bool }
    "x" Err!
    result.is-err
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) is True


def test_runtime_err_constructor_preserves_generic_error_values() -> None:
    checked = analyze_program(
        """module @app
  : err-string { -- r:Result<Int,String> }
    "abc" Err!
  ;
  : err-int { -- r:Result<Int,Int> }
    123 Err!
  ;
  : err-bool { -- r:Result<Int,Bool> }
    true Err!
  ;
  : err-list { -- r:Result<Int,List<String>> }
    ["x", "y"] Err!
  ;
  : err-map { -- r:Result<Int,Map<String,Int>> }
    map.empty:Map<String,Int>
    "k" 7 map.set
    Err!
  ;
  export : err-string
  export : err-int
  export : err-bool
  export : err-list
  export : err-map
end-module
"""
    )

    assert run_export(checked, "@app.err-string", RuntimeHostBindings({})) == Err("abc")
    assert run_export(checked, "@app.err-int", RuntimeHostBindings({})) == Err(123)
    assert run_export(checked, "@app.err-bool", RuntimeHostBindings({})) == Err(True)
    assert run_export(checked, "@app.err-list", RuntimeHostBindings({})) == Err(("x", "y"))
    assert run_export(checked, "@app.err-map", RuntimeHostBindings({})) == Err({"k": 7})


def test_runtime_result_unwrap_or_executes() -> None:
    checked = analyze_program(
        """module @app
  : ok { -- n:Int }
    [7]
    0
    list.get
    9
    result.unwrap-or
  ;
  : err { -- n:Int }
    []:List<Int>
    0
    list.get
    9
    result.unwrap-or
  ;
  export : ok
  export : err
end-module
"""
    )

    assert run_export(checked, "@app.ok", RuntimeHostBindings({})) == 7
    assert run_export(checked, "@app.err", RuntimeHostBindings({})) == 9


def test_runtime_map_len_executes() -> None:
    checked = analyze_program(
        """module @app
  : run { -- n:Int }
    map.empty:Map<String,Int>
    "a" 1 map.set
    "b" 2 map.set
    map.len
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({})) == 2


def test_runtime_map_is_empty_executes() -> None:
    checked = analyze_program(
        """module @app
  : empty { -- b:Bool }
    map.empty:Map<String,Int> map.is-empty
  ;
  : non-empty { -- b:Bool }
    map.empty:Map<String,Int> "a" 1 map.set map.is-empty
  ;
  export : empty
  export : non-empty
end-module
"""
    )

    assert run_export(checked, "@app.empty", RuntimeHostBindings({})) is True
    assert run_export(checked, "@app.non-empty", RuntimeHostBindings({})) is False


def test_runtime_map_keys_and_values_preserve_insertion_order() -> None:
    checked = analyze_program(
        """module @app
  : keys { -- xs:List<String> }
    map.empty:Map<String,Int>
    "a" 1 map.set
    "b" 2 map.set
    map.keys
  ;
  : values { -- xs:List<Int> }
    map.empty:Map<String,Int>
    "a" 1 map.set
    "b" 2 map.set
    map.values
  ;
  export : keys
  export : values
end-module
"""
    )

    assert run_export(checked, "@app.keys", RuntimeHostBindings({})) == ("a", "b")
    assert run_export(checked, "@app.values", RuntimeHostBindings({})) == (1, 2)


def test_runtime_if_false_executes_else_branch() -> None:
    checked = analyze_program(
        """module @app
  : run { -- }
    false
    if
      "yes" host.log
    else
      "no" host.log
    end
  ;
  export : run
end-module
""",
        host_contract=host_contract_from_words(
            [HostWord(name="host.log", signature=signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
"""), effect=HostEffect.PURE)]
        ),
    )

    seen: list[str] = []
    run_export(checked, "@app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}))

    assert seen == ["no"]


def test_runtime_if_can_call_nicole_word() -> None:
    host_contract = host_contract_from_words(
        [HostWord(name="host.log", signature=signature_from_source("""module @app
  : hostsig { msg:String -- } ;
end-module
"""), effect=HostEffect.PURE)]
    )
    checked = analyze_program(
        """module @app
  : log-yes { -- }
    "yes" host.log
  ;
  : run { flag:Bool -- }
    flag if
      log-yes
    else
      log-yes
    end
  ;
  export : run
end-module
""",
        host_contract=host_contract,
    )

    seen: list[str] = []
    run_export(checked, "@app.run", RuntimeHostBindings({"host.log": lambda msg: seen.append(msg)}), True)

    assert seen == ["yes"]


def test_runtime_if_can_produce_stack_output() -> None:
    checked = analyze_program(
        """module @app
  : choose { flag:Bool -- n:Int }
    flag if
      1
    else
      2
    end
  ;
  export : choose
end-module
"""
    )

    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), True) == 1
    assert run_export(checked, "@app.choose", RuntimeHostBindings({}), False) == 2


def test_runtime_nested_if_simple() -> None:
    checked = analyze_program(
        """module @app
  : run { flag:Bool -- n:Int }
    flag if
      true if
        1
      else
        2
      end
    else
      3
    end
  ;
  export : run
end-module
"""
    )

    assert run_export(checked, "@app.run", RuntimeHostBindings({}), True) == 1
    assert run_export(checked, "@app.run", RuntimeHostBindings({}), False) == 3
