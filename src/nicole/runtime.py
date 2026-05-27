from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from .ast_nodes import (
    BlockNode,
    CaseNode,
    IdentifierNode,
    IfNode,
    ListLiteralNode,
    LiteralNode,
    ModuleDeclaration,
    OperatorNode,
    PatternKind,
    PatternNode,
    ProgramNode,
    PropagateNode,
    QuoteNode,
    ResultErrNode,
    ResultOkNode,
    TypedEmptyListNode,
    TypedEmptyMapNode,
    TypeNode,
    WordDefNode,
)
from .pipeline import CheckedProgram
from .symbols import SymbolSource, WordSymbol
from .tokens import SourceSpan

__all__ = [
    "RuntimeFrameKind",
    "RuntimeFrame",
    "RuntimeStackTrace",
    "RuntimeDiagnosticSeverity",
    "RuntimeDiagnosticPhase",
    "RuntimeDiagnostic",
    "RuntimeError",
    "RuntimeStack",
    "RuntimeHostBindings",
    "UNIT",
    "Ok",
    "Err",
    "RuntimeOpaqueValue",
    "RuntimeQuote",
    "runtime_diagnostic",
    "render_runtime_diagnostic",
    "render_runtime_error",
    "run_export",
]


class _UnitValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNIT"


UNIT = _UnitValue()


class RuntimeDiagnosticSeverity(Enum):
    ERROR = "error"


class RuntimeDiagnosticPhase(Enum):
    RUNTIME = "runtime"


class RuntimeFrameKind(Enum):
    WORD = "word"
    QUOTATION = "quotation"
    HOST = "host"


@dataclass(frozen=True, slots=True)
class RuntimeFrame:
    call_kind: RuntimeFrameKind
    name: str
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class RuntimeStackTrace:
    _frames: tuple[RuntimeFrame, ...] = ()

    def __init__(self, frames: Iterable[RuntimeFrame] = ()) -> None:
        object.__setattr__(self, "_frames", tuple(frames))

    @property
    def frames(self) -> tuple[RuntimeFrame, ...]:
        return self._frames

    def append(self, frame: RuntimeFrame) -> RuntimeStackTrace:
        return RuntimeStackTrace((*self._frames, frame))

    def extend(self, frames: Iterable[RuntimeFrame]) -> RuntimeStackTrace:
        return RuntimeStackTrace((*self._frames, *tuple(frames)))

    def __len__(self) -> int:
        return len(self._frames)

    def __iter__(self):
        return iter(self._frames)


def _next_trace(
    current_trace: RuntimeStackTrace | None,
    frame: RuntimeFrame,
) -> RuntimeStackTrace:
    base_trace = RuntimeStackTrace() if current_trace is None else current_trace
    return base_trace.append(frame)


@dataclass(frozen=True, slots=True)
class RuntimeDiagnostic:
    severity: RuntimeDiagnosticSeverity
    phase: RuntimeDiagnosticPhase
    code: str
    message: str
    span: SourceSpan | None = None
    operation: str | None = None
    suggestion: str | None = None
    notes: tuple[str, ...] = ()
    cause: BaseException | None = None
    trace: RuntimeStackTrace | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes", tuple(self.notes))


def runtime_diagnostic(
    code: str,
    message: str,
    *,
    span: SourceSpan | None = None,
    operation: str | None = None,
    suggestion: str | None = None,
    notes: Iterable[str] = (),
    cause: BaseException | None = None,
    trace: RuntimeStackTrace | None = None,
) -> RuntimeDiagnostic:
    return RuntimeDiagnostic(
        severity=RuntimeDiagnosticSeverity.ERROR,
        phase=RuntimeDiagnosticPhase.RUNTIME,
        code=code,
        message=message,
        span=span,
        operation=operation,
        suggestion=suggestion,
        notes=tuple(notes),
        cause=cause,
        trace=trace,
    )


class RuntimeError(Exception):
    __slots__ = ("message", "diagnostics")

    message: str
    diagnostics: tuple[RuntimeDiagnostic, ...]

    def __init__(self, message: str, *, diagnostic: RuntimeDiagnostic | None = None) -> None:
        self.message = message
        effective_diagnostic = diagnostic
        if effective_diagnostic is None:
            effective_diagnostic = runtime_diagnostic(
                code="RUNTIME_ERROR",
                message=message,
            )
        self.diagnostics = (effective_diagnostic,)
        super().__init__(message)

    @property
    def diagnostic(self) -> RuntimeDiagnostic:
        return self.diagnostics[0]

    def __str__(self) -> str:
        return self.message


def render_runtime_diagnostic(diagnostic: RuntimeDiagnostic) -> str:
    lines = [f"RuntimeError[{diagnostic.code}]", diagnostic.message]
    if diagnostic.span is not None:
        lines.append(
            f"at {diagnostic.span.source.path}:{diagnostic.span.line}:{diagnostic.span.column}"
        )
    if diagnostic.operation is not None:
        lines.append(f"Operation: {diagnostic.operation}")
    if diagnostic.trace is not None and len(diagnostic.trace) > 0:
        lines.append("Stack trace:")
        for frame in diagnostic.trace:
            frame_line = f"at {frame.name}"
            if frame.span is not None:
                frame_line += (
                    f" ({frame.span.source.path}:{frame.span.line}:{frame.span.column})"
                )
            lines.append(frame_line)
    if diagnostic.notes:
        lines.append("Notes:")
        for note in diagnostic.notes:
            lines.append(f"- {note}")
    if diagnostic.cause is not None:
        lines.append(
            f"Cause: {diagnostic.cause.__class__.__name__}: {diagnostic.cause}"
        )
    return "\n".join(lines)


def render_runtime_error(error: RuntimeError) -> str:
    return render_runtime_diagnostic(error.diagnostic)


def _runtime_error(
    message: str,
    *,
    code: str,
    span: SourceSpan | None = None,
    operation: str | None = None,
    suggestion: str | None = None,
    notes: Iterable[str] = (),
    cause: BaseException | None = None,
    trace: RuntimeStackTrace | None = None,
) -> RuntimeError:
    return RuntimeError(
        message,
        diagnostic=runtime_diagnostic(
            code=code,
            message=message,
            span=span,
            operation=operation,
            suggestion=suggestion,
            notes=notes,
            cause=cause,
            trace=trace,
        ),
    )


@dataclass(frozen=True, slots=True)
class Ok:
    value: Any


@dataclass(frozen=True, slots=True)
class Err:
    error: str


@dataclass(frozen=True, slots=True)
class RuntimeOpaqueValue:
    type_name: str
    payload: object


@dataclass(frozen=True, slots=True)
class RuntimeQuote:
    node: QuoteNode
    captured_locals: Mapping[str, object]

@dataclass(frozen=True, slots=True)
class _FramePropagationSignal(Exception):
    error: str


@dataclass(frozen=True, slots=True)
class _SelfTailCallSignal(Exception):
    args: tuple[object, ...]


class RuntimeStack:
    def __init__(self) -> None:
        self._values: list[object] = []

    def push(self, value: object) -> None:
        self._values.append(value)

    def pop(self) -> object:
        if not self._values:
            raise _runtime_error(
                "runtime stack underflow",
                code="RUNTIME_STACK_UNDERFLOW",
                operation="stack.pop",
            )
        return self._values.pop()

    def peek(self) -> object:
        if not self._values:
            raise _runtime_error(
                "runtime stack underflow",
                code="RUNTIME_STACK_UNDERFLOW",
                operation="stack.peek",
            )
        return self._values[-1]

    def values(self) -> tuple[object, ...]:
        return tuple(self._values)


@dataclass(frozen=True, slots=True)
class RuntimeHostBindings:
    words: Mapping[str, Callable[..., object]]

    def __init__(self, words: Mapping[str, Callable[..., object]]) -> None:
        entries: dict[str, Callable[..., object]] = {}
        for name, binding in words.items():
            if not name.startswith("host."):
                message = f"runtime host binding must start with 'host.': {name}"
                raise _runtime_error(
                    message,
                    code="RUNTIME_RUNTIME_TYPE_ERROR",
                    operation="host.binding.validate",
                )
            if not callable(binding):
                message = f"runtime host binding must be callable: {name}"
                raise _runtime_error(
                    message,
                    code="RUNTIME_RUNTIME_TYPE_ERROR",
                    operation="host.binding.validate",
                )
            entries[name] = binding
        object.__setattr__(self, "words", MappingProxyType(entries))


def run_export(
    checked: CheckedProgram,
    export_name: str,
    runtime_bindings: RuntimeHostBindings,
    *args: object,
) -> object:
    from .interpreter import NicoleInterpreter

    interpreter = NicoleInterpreter(
        checked=checked,
        runtime_bindings=runtime_bindings,
    )
    return interpreter.run_export(export_name, *args)


def _run_export_checked(
    checked: CheckedProgram,
    export_name: str,
    runtime_bindings: RuntimeHostBindings,
    args: tuple[object, ...],
) -> object:
    export_word = checked.export_contract.words.get(export_name)
    if export_word is None:
        message = f"missing export: {export_name}"
        raise _runtime_error(
            message,
            code="RUNTIME_MISSING_EXPORT",
            operation="run_export",
        )

    word_index = _index_words(checked.program)
    export_def = word_index.get(export_word.internal_name)
    if export_def is None:
        message = f"missing export definition: {export_word.internal_name}"
        raise _runtime_error(
            message,
            code="RUNTIME_MISSING_EXPORT",
            operation="run_export",
        )

    return _invoke_word(
        export_def,
        word_index,
        runtime_bindings,
        args,
        current_word_name=export_word.internal_name,
    )


def _index_words(program: ProgramNode) -> dict[str, WordDefNode]:
    index: dict[str, WordDefNode] = {}

    for declaration in program.declarations:
        if not isinstance(declaration, ModuleDeclaration):
            continue
        module_name = ".".join(declaration.name.parts)
        for item in declaration.items:
            if isinstance(item, WordDefNode):
                _index_module_words(index, item, module_name=module_name, owner=None)
    return index


def _index_module_words(
    index: dict[str, WordDefNode],
    word: WordDefNode,
    *,
    module_name: str,
    owner: str | None,
) -> None:
    qualified = (
        f"@{module_name}.{word.name}"
        if owner is None
        else f"{owner}.{word.name}"
    )
    index[qualified] = word
    for nested in word.nested_words:
        _index_module_words(index, nested, module_name=module_name, owner=qualified)


def _invoke_word(
    word: WordDefNode,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    args: tuple[object, ...],
    *,
    current_word_name: str | None = None,
    current_trace: RuntimeStackTrace | None = None,
) -> object:
    expected_inputs = word.signature.inputs
    outputs = word.signature.outputs
    frame_word_name = current_word_name if current_word_name is not None else word.name
    word_trace = _next_trace(
        current_trace,
        RuntimeFrame(
            call_kind=RuntimeFrameKind.WORD,
            name=frame_word_name,
            span=word.span,
        ),
    )
    current_args = args

    while True:
        if len(current_args) != len(expected_inputs):
            message = f"wrong arity for {word.name}: expected {len(expected_inputs)}, got {len(current_args)}"
            raise _runtime_error(
                message,
                code="RUNTIME_RUNTIME_TYPE_ERROR",
                span=word.span,
                operation=word.name,
                trace=word_trace,
            )

        locals_env: dict[str, object] = {}
        for parameter, value in zip(expected_inputs, current_args):
            _ensure_matches_type(
                value,
                parameter.type_node,
                context=f"input '{parameter.name}'",
                trace=word_trace,
            )
            locals_env[parameter.name] = value

        stack = RuntimeStack()
        try:
            _execute_block(
                word.body,
                locals_env,
                stack,
                word_index,
                runtime_bindings,
                current_word_name=frame_word_name,
                current_trace=word_trace,
            )
            result_values = stack.values()
        except _SelfTailCallSignal as signal:
            current_args = signal.args
            continue
        except _FramePropagationSignal as signal:
            result_values = (Err(signal.error),)

        if len(result_values) != len(outputs):
            message = (
                f"wrong runtime signature for {word.name}: "
                f"expected {len(outputs)} outputs, got {len(result_values)}"
            )
            raise _runtime_error(
                message,
                code="RUNTIME_RUNTIME_TYPE_ERROR",
                span=word.span,
                operation=word.name,
                trace=word_trace,
            )
        for parameter, value in zip(outputs, result_values):
            _ensure_matches_type(
                value,
                parameter.type_node,
                context=f"output '{parameter.name}'",
                trace=word_trace,
            )

        if len(result_values) == 0:
            return None
        if len(result_values) == 1:
            return result_values[0]
        return result_values


def _execute_block(
    block: BlockNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    current_word_name: str | None = None,
    current_trace: RuntimeStackTrace | None = None,
) -> None:
    for item in block.items:
        if isinstance(item, LiteralNode):
            stack.push(item.value)
            continue
        if isinstance(item, TypedEmptyListNode):
            stack.push(())
            continue
        if isinstance(item, TypedEmptyMapNode):
            stack.push({})
            continue
        if isinstance(item, ListLiteralNode):
            _execute_list_literal(
                item,
                locals_env,
                stack,
                word_index,
                runtime_bindings,
                current_word_name=current_word_name,
                current_trace=current_trace,
            )
            continue
        if isinstance(item, ResultOkNode):
            value = stack.pop()
            stack.push(Ok(value))
            continue
        if isinstance(item, ResultErrNode):
            error = stack.pop()
            stack.push(Err(error))
            continue
        if isinstance(item, QuoteNode):
            stack.push(_create_runtime_quote(item, stack, current_trace=current_trace))
            continue
        if isinstance(item, OperatorNode):
            if item.operator == "call":
                _execute_call(
                    locals_env,
                    stack,
                    word_index,
                runtime_bindings,
                current_word_name=current_word_name,
                current_trace=current_trace,
                span=item.span,
            )
                continue
            if item.operator == "?":
                result_value = stack.pop()
                _ensure_matches_type(
                    result_value,
                    "Result",
                    context="? input",
                    trace=current_trace,
                )
                if isinstance(result_value, Ok):
                    stack.push(result_value.value)
                    continue
                raise _FramePropagationSignal(result_value.error)
            _execute_operator(
                item.operator,
                stack,
                span=item.span,
                current_trace=current_trace,
            )
            continue
        if isinstance(item, PropagateNode):
            result_value = stack.pop()
            _ensure_matches_type(
                result_value,
                "Result",
                context="? input",
                trace=current_trace,
            )
            if isinstance(result_value, Ok):
                stack.push(result_value.value)
                continue
            raise _FramePropagationSignal(result_value.error)
        if isinstance(item, IdentifierNode):
            _execute_identifier(
                item,
                locals_env,
                stack,
                word_index,
                runtime_bindings,
                current_word_name=current_word_name,
                current_trace=current_trace,
            )
            continue
        if isinstance(item, IfNode):
            _execute_if(
                item,
                locals_env,
                stack,
                word_index,
                runtime_bindings,
                current_word_name=current_word_name,
                current_trace=current_trace,
            )
            continue
        if isinstance(item, CaseNode):
            _execute_case(
                item,
                locals_env,
                stack,
                word_index,
                runtime_bindings,
                current_word_name=current_word_name,
                current_trace=current_trace,
            )
            continue
        message = f"runtime feature not supported: {type(item).__name__}"
        raise _runtime_error(
            message,
            code="RUNTIME_UNSUPPORTED_OPERATION",
            span=item.span,
            operation=type(item).__name__,
            trace=current_trace,
        )


def _execute_identifier(
    node: IdentifierNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    current_word_name: str | None = None,
    current_trace: RuntimeStackTrace | None = None,
) -> None:
    qualified_name = node.resolution.qualified_name
    if qualified_name is not None and qualified_name.startswith("local:"):
        local_name = qualified_name.split(":", 1)[1]
        stack.push(locals_env[local_name])
        return

    if node.resolution.owner_scope == "host":
        _execute_host_call(node, stack, runtime_bindings, current_trace=current_trace)
        return

    if node.name == "map.get":
        key = stack.pop()
        map_value = stack.pop()
        _ensure_matches_type(map_value, "Map", context="map.get map", trace=current_trace)
        _ensure_supported_map_key(key, context="map.get key", trace=current_trace)
        if key in map_value:
            stack.push(Ok(map_value[key]))
        else:
            stack.push(Err("MissingKey"))
        return
    if node.name == "map.contains":
        key = stack.pop()
        map_value = stack.pop()
        _ensure_matches_type(map_value, "Map", context="map.contains map", trace=current_trace)
        _ensure_supported_map_key(key, context="map.contains key", trace=current_trace)
        stack.push(key in map_value)
        return
    if node.name == "map.set":
        value = stack.pop()
        key = stack.pop()
        map_value = stack.pop()
        _ensure_matches_type(map_value, "Map", context="map.set map", trace=current_trace)
        _ensure_supported_map_key(key, context="map.set key", trace=current_trace)
        new_map = dict(map_value)
        new_map[key] = value
        stack.push(new_map)
        return
    if node.name == "map.remove":
        key = stack.pop()
        map_value = stack.pop()
        _ensure_matches_type(map_value, "Map", context="map.remove map", trace=current_trace)
        _ensure_supported_map_key(key, context="map.remove key", trace=current_trace)
        if key in map_value:
            new_map = dict(map_value)
            del new_map[key]
            stack.push(Ok(new_map))
        else:
            stack.push(Err("MissingKey"))
        return
    if node.name == "map.len":
        map_value = stack.pop()
        _ensure_matches_type(map_value, "Map", context="map.len map", trace=current_trace)
        stack.push(len(map_value))
        return
    if node.name == "map.is-empty":
        map_value = stack.pop()
        _ensure_matches_type(map_value, "Map", context="map.is-empty map", trace=current_trace)
        stack.push(len(map_value) == 0)
        return
    if node.name == "map.keys":
        map_value = stack.pop()
        _ensure_matches_type(map_value, "Map", context="map.keys map", trace=current_trace)
        stack.push(tuple(map_value.keys()))
        return
    if node.name == "map.values":
        map_value = stack.pop()
        _ensure_matches_type(map_value, "Map", context="map.values map", trace=current_trace)
        stack.push(tuple(map_value.values()))
        return
    if node.name == "result.is-ok":
        result_value = stack.pop()
        _ensure_matches_type(result_value, "Result", context="result.is-ok input", trace=current_trace)
        stack.push(isinstance(result_value, Ok))
        return
    if node.name == "result.is-err":
        result_value = stack.pop()
        _ensure_matches_type(result_value, "Result", context="result.is-err input", trace=current_trace)
        stack.push(isinstance(result_value, Err))
        return
    if node.name == "result.unwrap-or":
        fallback = stack.pop()
        result_value = stack.pop()
        _ensure_matches_type(result_value, "Result", context="result.unwrap-or input", trace=current_trace)
        if isinstance(result_value, Ok):
            stack.push(result_value.value)
        else:
            stack.push(fallback)
        return
    if node.name == "list.len":
        value = stack.pop()
        _ensure_matches_type(value, "List", context="list.len input", trace=current_trace)
        stack.push(len(value))
        return
    if node.name == "list.is-empty":
        value = stack.pop()
        _ensure_matches_type(value, "List", context="list.is-empty input", trace=current_trace)
        stack.push(len(value) == 0)
        return
    if node.name == "list.first":
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.first list", trace=current_trace)
        if len(list_value) == 0:
            stack.push(Err("OutOfBounds"))
            return
        stack.push(Ok(list_value[0]))
        return
    if node.name == "list.last":
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.last list", trace=current_trace)
        if len(list_value) == 0:
            stack.push(Err("OutOfBounds"))
            return
        stack.push(Ok(list_value[-1]))
        return
    if node.name == "list.append":
        value = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.append list", trace=current_trace)
        stack.push(list_value + (value,))
        return
    if node.name == "list.reverse":
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.reverse list", trace=current_trace)
        stack.push(tuple(reversed(list_value)))
        return
    if node.name == "list.set":
        value = stack.pop()
        index = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(index, "Int", context="list.set index", trace=current_trace)
        _ensure_matches_type(list_value, "List", context="list.set list", trace=current_trace)
        if 0 <= index < len(list_value):
            stack.push(Ok(list_value[:index] + (value,) + list_value[index + 1 :]))
        else:
            stack.push(Err("OutOfBounds"))
        return
    if node.name == "list.get":
        index = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(index, "Int", context="list.get index", trace=current_trace)
        _ensure_matches_type(list_value, "List", context="list.get list", trace=current_trace)
        if 0 <= index < len(list_value):
            stack.push(Ok(list_value[index]))
        else:
            stack.push(Err("OutOfBounds"))
        return
    if node.name == "list.concat":
        right = stack.pop()
        left = stack.pop()
        _ensure_matches_type(left, "List", context="list.concat left input", trace=current_trace)
        _ensure_matches_type(right, "List", context="list.concat right input", trace=current_trace)
        stack.push(left + right)
        return
    if node.name == "list.map":
        quote_value = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.map list", trace=current_trace)
        _ensure_matches_type(quote_value, "Quote", context="list.map quotation", trace=current_trace)
        mapped: list[object] = []
        for item in list_value:
            outputs = _invoke_runtime_quote_value(
                quote_value,
                (item,),
                word_index,
                runtime_bindings,
                current_trace=current_trace,
            )
            if len(outputs) != 1:
                message = (
                    "wrong runtime signature for list.map quotation: "
                    f"expected 1 output, got {len(outputs)}"
                )
                raise _runtime_error(
                    message,
                    code="RUNTIME_RUNTIME_TYPE_ERROR",
                    span=node.span,
                    operation="list.map",
                    trace=current_trace,
                )
            mapped.append(outputs[0])
        stack.push(tuple(mapped))
        return
    if node.name == "list.filter":
        quote_value = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.filter list", trace=current_trace)
        _ensure_matches_type(quote_value, "Quote", context="list.filter quotation", trace=current_trace)
        filtered: list[object] = []
        for item in list_value:
            outputs = _invoke_runtime_quote_value(
                quote_value,
                (item,),
                word_index,
                runtime_bindings,
                current_trace=current_trace,
            )
            if len(outputs) != 1:
                message = (
                    "wrong runtime signature for list.filter quotation: "
                    f"expected 1 output, got {len(outputs)}"
                )
                raise _runtime_error(
                    message,
                    code="RUNTIME_RUNTIME_TYPE_ERROR",
                    span=node.span,
                    operation="list.filter",
                    trace=current_trace,
                )
            decision = outputs[0]
            _ensure_matches_type(
                decision,
                "Bool",
                context="list.filter quotation output",
                trace=current_trace,
            )
            if decision:
                filtered.append(item)
        stack.push(tuple(filtered))
        return
    if node.name == "list.fold":
        quote_value = stack.pop()
        accumulator = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.fold list", trace=current_trace)
        _ensure_matches_type(quote_value, "Quote", context="list.fold quotation", trace=current_trace)
        for item in list_value:
            outputs = _invoke_runtime_quote_value(
                quote_value,
                (accumulator, item),
                word_index,
                runtime_bindings,
                current_trace=current_trace,
            )
            if len(outputs) != 1:
                message = (
                    "wrong runtime signature for list.fold quotation: "
                    f"expected 1 output, got {len(outputs)}"
                )
                raise _runtime_error(
                    message,
                    code="RUNTIME_RUNTIME_TYPE_ERROR",
                    span=node.span,
                    operation="list.fold",
                    trace=current_trace,
                )
            accumulator = outputs[0]
        stack.push(accumulator)
        return
    if node.name == "list.reduce":
        quote_value = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.reduce list", trace=current_trace)
        _ensure_matches_type(quote_value, "Quote", context="list.reduce quotation", trace=current_trace)
        if len(list_value) == 0:
            raise _runtime_error(
                "list.reduce cannot be applied to empty list at runtime",
                code="RUNTIME_RUNTIME_TYPE_ERROR",
                span=node.span,
                operation="list.reduce",
                trace=current_trace,
            )
        accumulator = list_value[0]
        for item in list_value[1:]:
            outputs = _invoke_runtime_quote_value(
                quote_value,
                (accumulator, item),
                word_index,
                runtime_bindings,
                current_trace=current_trace,
            )
            if len(outputs) != 1:
                message = (
                    "wrong runtime signature for list.reduce quotation: "
                    f"expected 1 output, got {len(outputs)}"
                )
                raise _runtime_error(
                    message,
                    code="RUNTIME_RUNTIME_TYPE_ERROR",
                    span=node.span,
                    operation="list.reduce",
                    trace=current_trace,
                )
            accumulator = outputs[0]
        stack.push(accumulator)
        return

    symbol = node.resolution.resolved_symbol
    if symbol is None:
        message = f"unresolved identifier at runtime: {node.name}"
        raise _runtime_error(
            message,
            code="RUNTIME_UNSUPPORTED_OPERATION",
            span=node.span,
            operation=node.name,
            trace=current_trace,
        )
    if isinstance(symbol, WordSymbol) and symbol.source is SymbolSource.BUILTIN:
        message = f"runtime feature not supported: builtin {node.name}"
        raise _runtime_error(
            message,
            code="RUNTIME_UNSUPPORTED_OPERATION",
            span=node.span,
            operation=node.name,
            trace=current_trace,
        )

    runtime_name = _runtime_symbol_name(symbol)
    word = word_index.get(runtime_name)
    if word is None:
        message = f"missing Nicole word definition at runtime: {runtime_name}"
        raise _runtime_error(
            message,
            code="RUNTIME_UNSUPPORTED_OPERATION",
            span=node.span,
            operation=runtime_name,
            trace=current_trace,
        )

    input_values: list[object] = []
    for _ in word.signature.inputs:
        input_values.append(stack.pop())
    input_values.reverse()
    next_args = tuple(input_values)
    if (
        node.resolution.is_self_tail_call
        and current_word_name is not None
        and runtime_name == current_word_name
    ):
        raise _SelfTailCallSignal(next_args)

    result = _invoke_word(
        word,
        word_index,
        runtime_bindings,
        next_args,
        current_word_name=runtime_name,
        current_trace=current_trace,
    )

    if len(word.signature.outputs) == 0:
        return
    if len(word.signature.outputs) == 1:
        stack.push(result)
        return
    if not isinstance(result, tuple):
        message = f"wrong runtime signature for {word.name}: expected tuple outputs"
        raise _runtime_error(
            message,
            code="RUNTIME_RUNTIME_TYPE_ERROR",
            span=node.span,
            operation=word.name,
            trace=current_trace,
        )
    for value in result:
        stack.push(value)


def _runtime_symbol_name(symbol: WordSymbol) -> str:
    if symbol.module is None:
        message = f"runtime symbol missing module ownership: {symbol.name}"
        raise _runtime_error(
            message,
            code="RUNTIME_UNSUPPORTED_OPERATION",
            operation=symbol.name,
        )
    return f"@{symbol.module}.{symbol.qualified_name}"


def _resolve_runtime_host_binding_name(
    node: IdentifierNode,
    *,
    trace: RuntimeStackTrace | None = None,
) -> str:
    # Bridge migration (B5B): prefer the explicit resolver bridge identity,
    # keep legacy node.name fallback for compatibility.
    if node.resolution.owner_scope == "host":
        host_binding_name = node.resolution.host_binding_name
        if host_binding_name is not None:
            return host_binding_name

    if node.name and node.name.startswith("host."):
        return node.name

    raise _runtime_error(
        "missing runtime host binding identity",
        code="RUNTIME_UNSUPPORTED_OPERATION",
        span=node.span,
        operation="host.binding.resolve",
        trace=trace,
    )


def _execute_host_call(
    node: IdentifierNode,
    stack: RuntimeStack,
    runtime_bindings: RuntimeHostBindings,
    *,
    current_trace: RuntimeStackTrace | None = None,
) -> None:
    runtime_host_binding_name = _resolve_runtime_host_binding_name(
        node,
        trace=current_trace,
    )
    host_name = (
        runtime_host_binding_name[5:]
        if runtime_host_binding_name.startswith("host.")
        else runtime_host_binding_name
    )
    host_trace = _next_trace(
        current_trace,
        RuntimeFrame(
            call_kind=RuntimeFrameKind.HOST,
            name=f"host:{host_name}",
            span=node.span,
        ),
    )
    signature = node.resolution.signature_reference
    if signature is None:
        message = f"missing runtime signature for host word: {runtime_host_binding_name}"
        raise _runtime_error(
            message,
            code="RUNTIME_UNSUPPORTED_OPERATION",
            span=node.span,
            operation=runtime_host_binding_name,
            trace=host_trace,
        )

    binding = runtime_bindings.words.get(runtime_host_binding_name)
    if binding is None:
        message = f"missing host binding: {runtime_host_binding_name}"
        raise _runtime_error(
            message,
            code="RUNTIME_HOST_BINDING_MISSING",
            span=node.span,
            operation=runtime_host_binding_name,
            trace=host_trace,
        )

    input_values: list[object] = []
    for parameter in reversed(signature.inputs):
        value = stack.pop()
        _ensure_matches_type(
            value,
            parameter.type_node,
            context=f"host input '{parameter.name}'",
            trace=host_trace,
        )
        input_values.append(value)
    input_values.reverse()

    try:
        result = binding(*input_values)
    except Exception as exc:  # pragma: no cover - defensive runtime boundary
        message = f"runtime host error: {runtime_host_binding_name}"
        raise _runtime_error(
            message,
            code="RUNTIME_HOST_FAILURE",
            span=node.span,
            operation=runtime_host_binding_name,
            cause=exc,
            trace=host_trace,
        ) from exc
    output_count = len(signature.outputs)
    if output_count == 0:
        return
    if output_count == 1:
        parameter = signature.outputs[0]
        _ensure_matches_type(
            result,
            parameter.type_node,
            context=f"host output '{parameter.name}'",
            trace=host_trace,
        )
        stack.push(result)
        return

    if not isinstance(result, tuple):
        message = (
            f"wrong runtime signature for host word {runtime_host_binding_name}: expected tuple outputs"
        )
        raise _runtime_error(
            message,
            code="RUNTIME_RUNTIME_TYPE_ERROR",
            span=node.span,
            operation=runtime_host_binding_name,
            trace=host_trace,
        )
    if len(result) != output_count:
        message = (
            f"wrong runtime signature for host word {runtime_host_binding_name}: "
            f"expected {output_count} outputs, got {len(result)}"
        )
        raise _runtime_error(
            message,
            code="RUNTIME_RUNTIME_TYPE_ERROR",
            span=node.span,
            operation=runtime_host_binding_name,
            trace=host_trace,
        )
    for parameter, value in zip(signature.outputs, result):
        _ensure_matches_type(
            value,
            parameter.type_node,
            context=f"host output '{parameter.name}'",
            trace=host_trace,
        )
        stack.push(value)


def _execute_if(
    node: IfNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    current_word_name: str | None = None,
    current_trace: RuntimeStackTrace | None = None,
) -> None:
    condition = stack.pop()
    _ensure_matches_type(condition, "Bool", context="if condition", trace=current_trace)
    if condition:
        _execute_block(
            node.then_block,
            locals_env,
            stack,
            word_index,
            runtime_bindings,
            current_word_name=current_word_name,
            current_trace=current_trace,
        )
        return
    _execute_block(
        node.else_block,
        locals_env,
        stack,
        word_index,
        runtime_bindings,
        current_word_name=current_word_name,
        current_trace=current_trace,
    )


def _execute_case(
    node: CaseNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    current_word_name: str | None = None,
    current_trace: RuntimeStackTrace | None = None,
) -> None:
    scrutinee = stack.pop()
    for branch in node.branches:
        matched, bound_name, bound_value = _match_case_pattern(branch.pattern, scrutinee)
        if not matched:
            continue
        branch_locals = dict(locals_env)
        if bound_name is not None:
            branch_locals[bound_name] = bound_value
        if branch.guard is not None:
            guard_stack = RuntimeStack()
            try:
                _execute_block(
                    branch.guard,
                    branch_locals,
                    guard_stack,
                    word_index,
                    runtime_bindings,
                    current_word_name=current_word_name,
                    current_trace=current_trace,
                )
            except _FramePropagationSignal as signal:
                raise _runtime_error(
                    "runtime case guard cannot propagate with ?",
                    code="RUNTIME_CASE_MATCH_FAILURE",
                    span=branch.guard.span,
                    operation="case.guard",
                    cause=signal,
                    trace=current_trace,
                ) from signal
            guard_values = guard_stack.values()
            if len(guard_values) != 1:
                raise _runtime_error(
                    "runtime case guard must produce exactly one Bool",
                    code="RUNTIME_RUNTIME_TYPE_ERROR",
                    span=branch.guard.span,
                    operation="case.guard",
                    trace=current_trace,
                )
            guard_value = guard_values[0]
            if not isinstance(guard_value, bool):
                raise _runtime_error(
                    "runtime case guard must produce Bool",
                    code="RUNTIME_RUNTIME_TYPE_ERROR",
                    span=branch.guard.span,
                    operation="case.guard",
                    trace=current_trace,
                )
            if not guard_value:
                continue
        _execute_block(
            branch.body,
            branch_locals,
            stack,
            word_index,
            runtime_bindings,
            current_word_name=current_word_name,
            current_trace=current_trace,
        )
        return
    raise _runtime_error(
        "runtime case match failure",
        code="RUNTIME_CASE_MATCH_FAILURE",
        span=node.span,
        operation="case",
        trace=current_trace,
    )


def _create_runtime_quote(
    node: QuoteNode,
    stack: RuntimeStack,
    *,
    current_trace: RuntimeStackTrace | None = None,
) -> RuntimeQuote:
    captured: dict[str, object] = {}
    for parameter in reversed(node.captures):
        value = stack.pop()
        _ensure_matches_type(
            value,
            parameter.type_node,
            context=f"quotation capture '{parameter.name}'",
            trace=current_trace,
        )
        captured[parameter.name] = value
    return RuntimeQuote(node=node, captured_locals=MappingProxyType(captured))


def _execute_call(
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    current_word_name: str | None = None,
    current_trace: RuntimeStackTrace | None = None,
    span: SourceSpan | None = None,
) -> None:
    quote_value = stack.pop()
    if not isinstance(quote_value, RuntimeQuote):
        raise _runtime_error(
            "call expects runtime quotation",
            code="RUNTIME_INVALID_QUOTATION",
            span=span,
            operation="call",
            trace=current_trace,
        )

    input_values: list[object] = []
    for _ in reversed(quote_value.node.inputs):
        input_values.append(stack.pop())
    input_values.reverse()
    result_values = _invoke_runtime_quote_value(
        quote_value,
        tuple(input_values),
        word_index,
        runtime_bindings,
        current_trace=current_trace,
    )
    for value in result_values:
        stack.push(value)

def _invoke_runtime_quote_value(
    quote_value: RuntimeQuote,
    input_values: tuple[object, ...],
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    *,
    current_trace: RuntimeStackTrace | None = None,
) -> tuple[object, ...]:
    quote = quote_value.node
    quote_trace = _next_trace(
        current_trace,
        RuntimeFrame(
            call_kind=RuntimeFrameKind.QUOTATION,
            name="quotation",
            span=quote.span,
        ),
    )
    if len(input_values) != len(quote.inputs):
        message = (
            "wrong runtime signature for quotation: "
            f"expected {len(quote.inputs)} inputs, got {len(input_values)}"
        )
        raise _runtime_error(
            message,
            code="RUNTIME_INVALID_QUOTATION",
            span=quote.span,
            operation="quote.call",
            trace=quote_trace,
        )
    for parameter, value in zip(quote.inputs, input_values):
        _ensure_matches_type(
            value,
            parameter.type_node,
            context=f"quotation input '{parameter.name}'",
            trace=quote_trace,
        )

    quote_locals = dict(quote_value.captured_locals)
    for parameter, value in zip(quote.inputs, input_values):
        quote_locals[parameter.name] = value

    quote_stack = RuntimeStack()
    try:
        _execute_block(
            quote.body,
            quote_locals,
            quote_stack,
            word_index,
            runtime_bindings,
            current_trace=quote_trace,
        )
        result_values = quote_stack.values()
    except _FramePropagationSignal as signal:
        result_values = (Err(signal.error),)
    if len(result_values) != len(quote.outputs):
        message = (
            "wrong runtime signature for quotation: "
            f"expected {len(quote.outputs)} outputs, got {len(result_values)}"
        )
        raise _runtime_error(
            message,
            code="RUNTIME_INVALID_QUOTATION",
            span=quote.span,
            operation="quote.call",
            trace=quote_trace,
        )
    for parameter, value in zip(quote.outputs, result_values):
        _ensure_matches_type(
            value,
            parameter.type_node,
            context=f"quotation output '{parameter.name}'",
            trace=quote_trace,
        )
    return result_values


def _execute_list_literal(
    node: ListLiteralNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    current_word_name: str | None = None,
    current_trace: RuntimeStackTrace | None = None,
) -> None:
    values: list[object] = []
    for element in node.elements:
        element_stack = RuntimeStack()
        _execute_block(
            BlockNode(span=element.span, items=(element,)),
            locals_env,
            element_stack,
            word_index,
            runtime_bindings,
            current_word_name=current_word_name,
            current_trace=current_trace,
        )
        element_values = element_stack.values()
        if len(element_values) != 1:
            raise _runtime_error(
                "list literal element must produce exactly one runtime value",
                code="RUNTIME_RUNTIME_TYPE_ERROR",
                span=node.span,
                operation="list.literal",
                trace=current_trace,
            )
        values.append(element_values[0])
    stack.push(tuple(values))


def _match_case_pattern(
    pattern: PatternNode,
    scrutinee: object,
) -> tuple[bool, str | None, object | None]:
    if pattern.kind is PatternKind.WILDCARD:
        return True, None, None
    if pattern.kind is PatternKind.LITERAL:
        return scrutinee == pattern.value, None, None
    if pattern.kind is PatternKind.OK:
        if not isinstance(scrutinee, Ok):
            return False, None, None
        if pattern.binding is None:
            return True, None, None
        return True, pattern.binding, scrutinee.value
    if pattern.kind is PatternKind.ERR:
        if not isinstance(scrutinee, Err):
            return False, None, None
        if pattern.binding is not None:
            return True, pattern.binding, scrutinee.error
        if isinstance(pattern.value, str):
            return scrutinee.error == pattern.value, None, None
        return True, None, None
    if pattern.kind is PatternKind.NAME:
        if pattern.value == "MissingKey":
            return scrutinee == "MissingKey", None, None
        if pattern.value == "OutOfBounds":
            return scrutinee == "OutOfBounds", None, None
        return False, None, None
    return False, None, None


def _execute_operator(
    operator: str,
    stack: RuntimeStack,
    *,
    span: SourceSpan | None = None,
    current_trace: RuntimeStackTrace | None = None,
) -> None:
    if operator == "drop":
        stack.pop()
        return
    if operator == "dup":
        value = stack.pop()
        stack.push(value)
        stack.push(value)
        return
    if operator == "swap":
        right = stack.pop()
        left = stack.pop()
        stack.push(right)
        stack.push(left)
        return
    if operator == "over":
        right = stack.pop()
        left = stack.pop()
        stack.push(left)
        stack.push(right)
        stack.push(left)
        return
    if operator == "rot":
        third = stack.pop()
        second = stack.pop()
        first = stack.pop()
        stack.push(second)
        stack.push(third)
        stack.push(first)
        return

    if operator in {"+", "-", "*", "div", "mod"}:
        right = stack.pop()
        left = stack.pop()
        operation = "divide" if operator == "div" else "modulo" if operator == "mod" else "arithmetic"
        _ensure_matches_type(
            left,
            "Int",
            context="left operand",
            span=span,
            operation=operation,
            trace=current_trace,
        )
        _ensure_matches_type(
            right,
            "Int",
            context="right operand",
            span=span,
            operation=operation,
            trace=current_trace,
        )
        try:
            if operator == "+":
                stack.push(left + right)
            elif operator == "-":
                stack.push(left - right)
            elif operator == "*":
                stack.push(left * right)
            elif operator == "div":
                stack.push(left // right)
            else:
                stack.push(left % right)
        except ZeroDivisionError as exc:
            message = f"runtime arithmetic error: {operator} by zero"
            operation = "divide" if operator == "div" else "modulo" if operator == "mod" else operator
            raise _runtime_error(
                message,
                code="RUNTIME_DIVISION_BY_ZERO",
                span=span,
                operation=operation,
                cause=exc,
                trace=current_trace,
            ) from exc
        return

    if operator in {"+.", "-.", "*.", "/."}:
        right = stack.pop()
        left = stack.pop()
        _ensure_matches_type(
            left,
            "Float",
            context="left operand",
            span=span,
            operation="divide",
            trace=current_trace,
        )
        _ensure_matches_type(
            right,
            "Float",
            context="right operand",
            span=span,
            operation="divide",
            trace=current_trace,
        )
        try:
            if operator == "+.":
                stack.push(left + right)
            elif operator == "-.":
                stack.push(left - right)
            elif operator == "*.":
                stack.push(left * right)
            else:
                stack.push(left / right)
        except ZeroDivisionError as exc:
            message = f"runtime arithmetic error: {operator} by zero"
            raise _runtime_error(
                message,
                code="RUNTIME_DIVISION_BY_ZERO",
                span=span,
                operation="divide",
                cause=exc,
                trace=current_trace,
            ) from exc
        return

    if operator in {"<", "<=", ">", ">="}:
        right = stack.pop()
        left = stack.pop()
        if type(left) is int and type(right) is int:
            if operator == "<":
                stack.push(left < right)
            elif operator == "<=":
                stack.push(left <= right)
            elif operator == ">":
                stack.push(left > right)
            else:
                stack.push(left >= right)
            return
        if type(left) is float and type(right) is float:
            if operator == "<":
                stack.push(left < right)
            elif operator == "<=":
                stack.push(left <= right)
            elif operator == ">":
                stack.push(left > right)
            else:
                stack.push(left >= right)
            return
        raise _runtime_error(
            "wrong runtime signature for comparison operands: expected Int/Int or Float/Float",
            code="RUNTIME_INVALID_COMPARISON",
            span=span,
            operation="compare",
            trace=current_trace,
        )

    if operator in {"=", "!="}:
        right = stack.pop()
        left = stack.pop()
        if _is_runtime_opaque_value(left) or _is_runtime_opaque_value(right):
            raise _runtime_error(
                "equality is not supported for host opaque values",
                code="RUNTIME_INVALID_COMPARISON",
                span=span,
                operation="compare",
                trace=current_trace,
            )
        if type(left) is not type(right):
            raise _runtime_error(
                "wrong runtime signature for equality operands: expected matching types",
                code="RUNTIME_INVALID_COMPARISON",
                span=span,
                operation="compare",
                trace=current_trace,
            )
        if operator == "=":
            stack.push(left == right)
        else:
            stack.push(left != right)
        return

    if operator in {"and", "or"}:
        right = stack.pop()
        left = stack.pop()
        _ensure_matches_type(
            left,
            "Bool",
            context="left operand",
            span=span,
            operation=operator,
            trace=current_trace,
        )
        _ensure_matches_type(
            right,
            "Bool",
            context="right operand",
            span=span,
            operation=operator,
            trace=current_trace,
        )
        if operator == "and":
            stack.push(left and right)
        else:
            stack.push(left or right)
        return

    if operator == "not":
        value = stack.pop()
        _ensure_matches_type(
            value,
            "Bool",
            context="operand",
            span=span,
            operation=operator,
            trace=current_trace,
        )
        stack.push(not value)
        return

    message = f"runtime feature not supported: operator {operator}"
    raise _runtime_error(
        message,
        code="RUNTIME_UNSUPPORTED_OPERATION",
        span=span,
        operation=operator,
        trace=current_trace,
    )


def _ensure_matches_type(
    value: object,
    type_spec: str | TypeNode,
    *,
    context: str,
    span: SourceSpan | None = None,
    operation: str | None = None,
    trace: RuntimeStackTrace | None = None,
) -> None:
    expected = _describe_type(type_spec)
    if _matches_type(value, type_spec, trace=trace):
        return
    message = f"wrong runtime signature for {context}: expected {expected}"
    raise _runtime_error(
        message,
        code="RUNTIME_RUNTIME_TYPE_ERROR",
        span=span,
        operation=operation if operation is not None else context,
        trace=trace,
    )


def _matches_type(
    value: object,
    type_spec: str | TypeNode,
    *,
    trace: RuntimeStackTrace | None = None,
) -> bool:
    if isinstance(type_spec, TypeNode):
        type_name = type_spec.name
        if type_name == "List":
            if not _matches_type_name(value, "List", trace=trace):
                return False
            if len(type_spec.args) != 1 or not isinstance(type_spec.args[0], TypeNode):
                raise _runtime_error(
                    "runtime feature not supported: type List",
                    code="RUNTIME_UNSUPPORTED_OPERATION",
                    operation="type.List",
                    trace=trace,
                )
            item_type = type_spec.args[0]
            return all(_matches_type(item, item_type, trace=trace) for item in value)

        if type_name == "Map":
            if not _matches_type_name(value, "Map", trace=trace):
                return False
            if len(type_spec.args) != 2:
                raise _runtime_error(
                    "runtime feature not supported: type Map",
                    code="RUNTIME_UNSUPPORTED_OPERATION",
                    operation="type.Map",
                    trace=trace,
                )
            key_type = type_spec.args[0]
            value_type = type_spec.args[1]
            if not isinstance(key_type, TypeNode) or not isinstance(value_type, TypeNode):
                raise _runtime_error(
                    "runtime feature not supported: type Map",
                    code="RUNTIME_UNSUPPORTED_OPERATION",
                    operation="type.Map",
                    trace=trace,
                )
            return all(
                _matches_type(k, key_type, trace=trace) and _matches_type(v, value_type, trace=trace)
                for k, v in value.items()
            )

        if type_name == "Result":
            if len(type_spec.args) != 2:
                raise _runtime_error(
                    "runtime feature not supported: type Result",
                    code="RUNTIME_UNSUPPORTED_OPERATION",
                    operation="type.Result",
                    trace=trace,
                )
            ok_type = type_spec.args[0]
            err_type = type_spec.args[1]
            if not isinstance(ok_type, TypeNode) or not isinstance(err_type, TypeNode):
                raise _runtime_error(
                    "runtime feature not supported: type Result",
                    code="RUNTIME_UNSUPPORTED_OPERATION",
                    operation="type.Result",
                    trace=trace,
                )
            if isinstance(value, Ok):
                return _matches_type(value.value, ok_type, trace=trace)
            if isinstance(value, Err):
                return _matches_type(value.error, err_type, trace=trace)
            return False

        return _matches_type_name(value, type_name, trace=trace)

    return _matches_type_name(value, type_spec, trace=trace)


def _matches_type_name(
    value: object,
    type_name: str,
    *,
    trace: RuntimeStackTrace | None = None,
) -> bool:
    if type_name == "Int":
        return type(value) is int
    if type_name == "Float":
        return type(value) is float
    if type_name == "String":
        return isinstance(value, str)
    if type_name == "Bool":
        return type(value) is bool
    if type_name == "Unit":
        return value is UNIT
    if type_name in {"Quote", "DirtyQuote"}:
        return isinstance(value, RuntimeQuote)
    if type_name == "Result":
        return isinstance(value, (Ok, Err))
    if type_name == "List":
        return isinstance(value, tuple)
    if type_name == "Map":
        return isinstance(value, dict)
    if type_name == "MapError":
        return value == "MissingKey"
    if type_name == "ListError":
        return value == "OutOfBounds"
    if type_name.startswith("host."):
        return _matches_runtime_opaque_value(value, expected_type_name=type_name)
    message = f"runtime feature not supported: type {type_name}"
    raise _runtime_error(
        message,
        code="RUNTIME_UNSUPPORTED_OPERATION",
        operation=f"type.{type_name}",
        trace=trace,
    )


def _describe_type(type_spec: str | TypeNode) -> str:
    if isinstance(type_spec, str):
        return type_spec
    if not type_spec.args:
        return type_spec.name
    rendered_args: list[str] = []
    for argument in type_spec.args:
        if isinstance(argument, TypeNode):
            rendered_args.append(_describe_type(argument))
        else:
            rendered_args.append("...")
    return f"{type_spec.name}<{', '.join(rendered_args)}>"


def _ensure_supported_map_key(
    value: object,
    *,
    context: str,
    trace: RuntimeStackTrace | None = None,
) -> None:
    if type(value) is int:
        return
    if isinstance(value, str):
        return
    if type(value) is bool:
        return
    message = f"wrong runtime signature for {context}: expected Int/String/Bool"
    raise _runtime_error(
        message,
        code="RUNTIME_RUNTIME_TYPE_ERROR",
        operation=context,
        trace=trace,
    )


def _is_runtime_opaque_value(value: object) -> bool:
    return isinstance(value, RuntimeOpaqueValue)


def _matches_runtime_opaque_value(value: object, *, expected_type_name: str) -> bool:
    if not isinstance(value, RuntimeOpaqueValue):
        return False
    if type(value.type_name) is not str:
        return False
    return value.type_name == expected_type_name
