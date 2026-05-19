from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .ast_nodes import (
    BlockNode,
    CaseNode,
    IdentifierNode,
    IfNode,
    ListLiteralNode,
    LiteralNode,
    OperatorNode,
    PatternKind,
    PatternNode,
    QuoteNode,
    TypedEmptyListNode,
    WordDefNode,
)
from .pipeline import CheckedProgram
from .symbols import SymbolSource, WordSymbol

__all__ = [
    "RuntimeError",
    "RuntimeStack",
    "RuntimeHostBindings",
    "Ok",
    "Err",
    "RuntimeQuote",
    "run_export",
]


@dataclass(slots=True)
class RuntimeError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class Ok:
    value: Any


@dataclass(frozen=True, slots=True)
class Err:
    error: str


@dataclass(frozen=True, slots=True)
class RuntimeQuote:
    node: QuoteNode
    captured_locals: Mapping[str, object]


class RuntimeStack:
    def __init__(self) -> None:
        self._values: list[object] = []

    def push(self, value: object) -> None:
        self._values.append(value)

    def pop(self) -> object:
        if not self._values:
            raise RuntimeError("runtime stack underflow")
        return self._values.pop()

    def peek(self) -> object:
        if not self._values:
            raise RuntimeError("runtime stack underflow")
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
                raise RuntimeError(f"runtime host binding must start with 'host.': {name}")
            if not callable(binding):
                raise RuntimeError(f"runtime host binding must be callable: {name}")
            entries[name] = binding
        object.__setattr__(self, "words", MappingProxyType(entries))


def run_export(
    checked: CheckedProgram,
    export_name: str,
    runtime_bindings: RuntimeHostBindings,
    *args: object,
) -> object:
    export_word = checked.export_contract.words.get(export_name)
    if export_word is None:
        raise RuntimeError(f"missing export: {export_name}")

    word_index = _index_words(checked.program.words)
    export_def = word_index.get(export_word.internal_name)
    if export_def is None:
        raise RuntimeError(f"missing export definition: {export_word.internal_name}")

    return _invoke_word(export_def, word_index, runtime_bindings, args)


def _index_words(words: tuple[WordDefNode, ...], owner: str | None = None) -> dict[str, WordDefNode]:
    index: dict[str, WordDefNode] = {}
    for word in words:
        qualified = word.name if owner is None else f"{owner}.{word.name}"
        index[qualified] = word
        index.update(_index_words(word.nested_words, owner=qualified))
    return index


def _invoke_word(
    word: WordDefNode,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
    args: tuple[object, ...],
) -> object:
    expected_inputs = word.signature.inputs
    if len(args) != len(expected_inputs):
        raise RuntimeError(
            f"wrong arity for {word.name}: expected {len(expected_inputs)}, got {len(args)}"
        )

    locals_env: dict[str, object] = {}
    for parameter, value in zip(expected_inputs, args):
        _ensure_matches_type(value, parameter.type_node.name, context=f"input '{parameter.name}'")
        locals_env[parameter.name] = value

    stack = RuntimeStack()
    _execute_block(word.body, locals_env, stack, word_index, runtime_bindings)

    outputs = word.signature.outputs
    result_values = stack.values()
    if len(result_values) != len(outputs):
        raise RuntimeError(
            f"wrong runtime signature for {word.name}: expected {len(outputs)} outputs, got {len(result_values)}"
        )
    for parameter, value in zip(outputs, result_values):
        _ensure_matches_type(value, parameter.type_node.name, context=f"output '{parameter.name}'")

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
) -> None:
    for item in block.items:
        if isinstance(item, LiteralNode):
            stack.push(item.value)
            continue
        if isinstance(item, TypedEmptyListNode):
            stack.push(())
            continue
        if isinstance(item, ListLiteralNode):
            _execute_list_literal(item, locals_env, stack, word_index, runtime_bindings)
            continue
        if isinstance(item, QuoteNode):
            stack.push(_create_runtime_quote(item, stack))
            continue
        if isinstance(item, OperatorNode):
            if item.operator == "call":
                _execute_call(locals_env, stack, word_index, runtime_bindings)
                continue
            _execute_operator(item.operator, stack)
            continue
        if isinstance(item, IdentifierNode):
            _execute_identifier(item, locals_env, stack, word_index, runtime_bindings)
            continue
        if isinstance(item, IfNode):
            _execute_if(item, locals_env, stack, word_index, runtime_bindings)
            continue
        if isinstance(item, CaseNode):
            _execute_case(item, locals_env, stack, word_index, runtime_bindings)
            continue
        raise RuntimeError(f"runtime feature not supported: {type(item).__name__}")


def _execute_identifier(
    node: IdentifierNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
) -> None:
    qualified_name = node.resolution.qualified_name
    if qualified_name is not None and qualified_name.startswith("local:"):
        local_name = qualified_name.split(":", 1)[1]
        stack.push(locals_env[local_name])
        return

    if node.resolution.owner_scope == "host":
        _execute_host_call(node, stack, runtime_bindings)
        return

    if node.name == "list.len":
        value = stack.pop()
        _ensure_matches_type(value, "List", context="list.len input")
        stack.push(len(value))
        return
    if node.name == "list.push":
        value = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(list_value, "List", context="list.push list")
        stack.push(list_value + (value,))
        return
    if node.name == "list.set":
        value = stack.pop()
        index = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(index, "Int", context="list.set index")
        _ensure_matches_type(list_value, "List", context="list.set list")
        if 0 <= index < len(list_value):
            stack.push(Ok(list_value[:index] + (value,) + list_value[index + 1 :]))
        else:
            stack.push(Err("OutOfBounds"))
        return
    if node.name == "list.get":
        index = stack.pop()
        list_value = stack.pop()
        _ensure_matches_type(index, "Int", context="list.get index")
        _ensure_matches_type(list_value, "List", context="list.get list")
        if 0 <= index < len(list_value):
            stack.push(Ok(list_value[index]))
        else:
            stack.push(Err("OutOfBounds"))
        return
    if node.name == "list.concat":
        right = stack.pop()
        left = stack.pop()
        _ensure_matches_type(left, "List", context="list.concat left input")
        _ensure_matches_type(right, "List", context="list.concat right input")
        stack.push(left + right)
        return

    symbol = node.resolution.resolved_symbol
    if symbol is None:
        raise RuntimeError(f"unresolved identifier at runtime: {node.name}")
    if isinstance(symbol, WordSymbol) and symbol.source is SymbolSource.BUILTIN:
        raise RuntimeError(f"runtime feature not supported: builtin {node.name}")

    word = word_index.get(symbol.qualified_name)
    if word is None:
        raise RuntimeError(f"missing Nicole word definition at runtime: {symbol.qualified_name}")

    input_values: list[object] = []
    for _ in word.signature.inputs:
        input_values.append(stack.pop())
    input_values.reverse()
    result = _invoke_word(word, word_index, runtime_bindings, tuple(input_values))

    if len(word.signature.outputs) == 0:
        return
    if len(word.signature.outputs) == 1:
        stack.push(result)
        return
    if not isinstance(result, tuple):
        raise RuntimeError(f"wrong runtime signature for {word.name}: expected tuple outputs")
    for value in result:
        stack.push(value)


def _execute_host_call(node: IdentifierNode, stack: RuntimeStack, runtime_bindings: RuntimeHostBindings) -> None:
    signature = node.resolution.signature_reference
    if signature is None:
        raise RuntimeError(f"missing runtime signature for host word: {node.name}")

    binding = runtime_bindings.words.get(node.name)
    if binding is None:
        raise RuntimeError(f"missing host binding: {node.name}")

    input_values: list[object] = []
    for parameter in reversed(signature.inputs):
        value = stack.pop()
        _ensure_matches_type(value, parameter.type_node.name, context=f"host input '{parameter.name}'")
        input_values.append(value)
    input_values.reverse()

    try:
        result = binding(*input_values)
    except Exception as exc:  # pragma: no cover - defensive runtime boundary
        raise RuntimeError(f"runtime host error: {node.name}") from exc
    output_count = len(signature.outputs)
    if output_count == 0:
        return
    if output_count == 1:
        parameter = signature.outputs[0]
        _ensure_matches_type(result, parameter.type_node.name, context=f"host output '{parameter.name}'")
        stack.push(result)
        return

    if not isinstance(result, tuple):
        raise RuntimeError(f"wrong runtime signature for host word {node.name}: expected tuple outputs")
    if len(result) != output_count:
        raise RuntimeError(
            f"wrong runtime signature for host word {node.name}: expected {output_count} outputs, got {len(result)}"
        )
    for parameter, value in zip(signature.outputs, result):
        _ensure_matches_type(value, parameter.type_node.name, context=f"host output '{parameter.name}'")
        stack.push(value)


def _execute_if(
    node: IfNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
) -> None:
    condition = stack.pop()
    _ensure_matches_type(condition, "Bool", context="if condition")
    if condition:
        _execute_block(node.then_block, locals_env, stack, word_index, runtime_bindings)
        return
    _execute_block(node.else_block, locals_env, stack, word_index, runtime_bindings)


def _execute_case(
    node: CaseNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
) -> None:
    scrutinee = stack.pop()
    for branch in node.branches:
        matched, bound_name, bound_value = _match_case_pattern(branch.pattern, scrutinee)
        if not matched:
            continue
        branch_locals = dict(locals_env)
        if bound_name is not None:
            branch_locals[bound_name] = bound_value
        _execute_block(branch.body, branch_locals, stack, word_index, runtime_bindings)
        return
    raise RuntimeError("runtime case match failure")


def _create_runtime_quote(node: QuoteNode, stack: RuntimeStack) -> RuntimeQuote:
    captured: dict[str, object] = {}
    for parameter in reversed(node.captures):
        value = stack.pop()
        _ensure_matches_type(value, parameter.type_node.name, context=f"quotation capture '{parameter.name}'")
        captured[parameter.name] = value
    return RuntimeQuote(node=node, captured_locals=MappingProxyType(captured))


def _execute_call(
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
) -> None:
    quote_value = stack.pop()
    if not isinstance(quote_value, RuntimeQuote):
        raise RuntimeError("call expects runtime quotation")

    quote = quote_value.node
    input_values: list[object] = []
    for parameter in reversed(quote.inputs):
        value = stack.pop()
        _ensure_matches_type(value, parameter.type_node.name, context=f"quotation input '{parameter.name}'")
        input_values.append(value)
    input_values.reverse()

    quote_locals = dict(quote_value.captured_locals)
    for parameter, value in zip(quote.inputs, input_values):
        quote_locals[parameter.name] = value

    quote_stack = RuntimeStack()
    _execute_block(quote.body, quote_locals, quote_stack, word_index, runtime_bindings)

    result_values = quote_stack.values()
    if len(result_values) != len(quote.outputs):
        raise RuntimeError(
            "wrong runtime signature for quotation: "
            f"expected {len(quote.outputs)} outputs, got {len(result_values)}"
        )
    for parameter, value in zip(quote.outputs, result_values):
        _ensure_matches_type(value, parameter.type_node.name, context=f"quotation output '{parameter.name}'")
        stack.push(value)


def _execute_list_literal(
    node: ListLiteralNode,
    locals_env: dict[str, object],
    stack: RuntimeStack,
    word_index: dict[str, WordDefNode],
    runtime_bindings: RuntimeHostBindings,
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
        )
        element_values = element_stack.values()
        if len(element_values) != 1:
            raise RuntimeError("list literal element must produce exactly one runtime value")
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


def _execute_operator(operator: str, stack: RuntimeStack) -> None:
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

    if operator in {"+", "-", "*", "div", "mod"}:
        right = stack.pop()
        left = stack.pop()
        _ensure_matches_type(left, "Int", context="left operand")
        _ensure_matches_type(right, "Int", context="right operand")
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
            raise RuntimeError(f"runtime arithmetic error: {operator} by zero") from exc
        return

    if operator in {"+.", "-.", "*.", "/."}:
        right = stack.pop()
        left = stack.pop()
        _ensure_matches_type(left, "Float", context="left operand")
        _ensure_matches_type(right, "Float", context="right operand")
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
            raise RuntimeError(f"runtime arithmetic error: {operator} by zero") from exc
        return

    raise RuntimeError(f"runtime feature not supported: operator {operator}")


def _ensure_matches_type(value: object, type_name: str, *, context: str) -> None:
    if type_name == "Int":
        ok = type(value) is int
    elif type_name == "Float":
        ok = type(value) is float
    elif type_name == "String":
        ok = isinstance(value, str)
    elif type_name == "Bool":
        ok = type(value) is bool
    elif type_name == "Quote":
        ok = isinstance(value, RuntimeQuote)
    elif type_name == "Result":
        ok = isinstance(value, (Ok, Err))
    elif type_name == "List":
        ok = isinstance(value, tuple)
    elif type_name == "MapError":
        ok = value == "MissingKey"
    elif type_name == "ListError":
        ok = value == "OutOfBounds"
    else:
        raise RuntimeError(f"runtime feature not supported: type {type_name}")

    if ok:
        return
    raise RuntimeError(f"wrong runtime signature for {context}: expected {type_name}")
