from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Callable

from .ast_nodes import (
    BlockNode,
    CaseNode,
    IdentifierNode,
    IfNode,
    ModuleDeclaration,
    ListLiteralNode,
    LiteralKind,
    LiteralNode,
    OperatorNode,
    PatternKind,
    PropagateNode,
    ProgramNode,
    QuoteEffect,
    QuoteNode,
    QuoteTypeNode,
    ResultErrNode,
    ResultOkNode,
    TypeNode,
    TypedEmptyListNode,
    TypedEmptyMapNode,
    WordDefNode,
)
from .errors import DiagnosticError, DiagnosticPhase
from .host_abi import HostABIError, HostEffect, validate_type_v1
from .symbols import SymbolCategory, SymbolSource, SymbolTable, WordSymbol
from .tokens import SourceSpan

__all__ = ["Checker", "CheckerError", "check", "check_program"]

_LANGUAGE_SCALAR_TYPES_V1 = {
    "Int",
    "Float",
    "String",
    "Bool",
    "Unit",
    "ListError",
    "MapError",
}


class CheckerError(DiagnosticError):
    phase = DiagnosticPhase.CHECKER
    default_code = "CHECKER_ERROR"


@dataclass(frozen=True, slots=True)
class StackValue:
    type_node: TypeNode
    known_empty_list: bool = False


@dataclass(frozen=True, slots=True)
class WordEffectInfo:
    declared_dirty: bool
    inferred_dirty: bool
    direct_dirty_source: bool


@dataclass(frozen=True, slots=True)
class _CallEdge:
    caller: str
    callee: str
    line: int
    column: int
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class EffectAnalysisResult:
    effects: dict[str, WordEffectInfo]
    calls_by_word: dict[str, tuple[_CallEdge, ...]]
    word_order: tuple[str, ...]
    word_spans: dict[str, SourceSpan]


class Checker:
    def __init__(
        self,
        symbols: SymbolTable,
        *,
        declared_opaque_type_names: frozenset[str] = frozenset(),
    ) -> None:
        self._symbols = symbols
        self._declared_opaque_type_names = frozenset(declared_opaque_type_names)

    def check(self, program: ProgramNode) -> ProgramNode:
        self._validate_program_types(program)
        for word in self._iter_top_level_words(program):
            self._check_word(word)
        self._mark_direct_self_tail_calls(program)
        effect_analysis = self._analyze_effects(program)
        self._validate_case_guard_purity(program, effect_analysis)
        self._validate_quote_effect_restrictions(program, effect_analysis)
        self._validate_effect_annotations(effect_analysis)
        self._validate_pure_to_dirty_calls(effect_analysis)
        return program

    def _validate_program_types(self, program: ProgramNode) -> None:
        for declaration in program.declarations:
            if not isinstance(declaration, ModuleDeclaration):
                continue
            module_name = ".".join(declaration.name.parts)
            for item in declaration.items:
                if isinstance(item, WordDefNode):
                    self._validate_word_types(item, module_name=module_name)

    def _validate_word_types(self, word: WordDefNode, *, module_name: str) -> None:
        self._validate_signature_types(word.signature, module_name=module_name)
        self._validate_block_types(word.body, module_name=module_name)
        for nested_word in word.nested_words:
            self._validate_word_types(nested_word, module_name=module_name)

    def _validate_signature_types(self, signature, *, module_name: str) -> None:
        for parameter in signature.inputs:
            self._validate_type_node(parameter.type_node, module_name=module_name)
        for parameter in signature.outputs:
            self._validate_type_node(parameter.type_node, module_name=module_name)

    def _validate_block_types(self, block: BlockNode, *, module_name: str) -> None:
        for item in block.items:
            if isinstance(item, TypedEmptyListNode):
                self._validate_type_node(item.type_node, module_name=module_name)
                continue
            if isinstance(item, TypedEmptyMapNode):
                self._validate_type_node(item.type_node, module_name=module_name)
                continue
            if isinstance(item, QuoteNode):
                for parameter in item.captures:
                    self._validate_type_node(parameter.type_node, module_name=module_name)
                for parameter in item.inputs:
                    self._validate_type_node(parameter.type_node, module_name=module_name)
                for parameter in item.outputs:
                    self._validate_type_node(parameter.type_node, module_name=module_name)
                self._validate_block_types(item.body, module_name=module_name)
                continue
            if isinstance(item, ListLiteralNode):
                for element in item.elements:
                    if isinstance(element, QuoteNode):
                        for parameter in element.captures:
                            self._validate_type_node(parameter.type_node, module_name=module_name)
                        for parameter in element.inputs:
                            self._validate_type_node(parameter.type_node, module_name=module_name)
                        for parameter in element.outputs:
                            self._validate_type_node(parameter.type_node, module_name=module_name)
                        self._validate_block_types(element.body, module_name=module_name)
                    elif isinstance(element, TypedEmptyListNode):
                        self._validate_type_node(element.type_node, module_name=module_name)
                    elif isinstance(element, TypedEmptyMapNode):
                        self._validate_type_node(element.type_node, module_name=module_name)
                continue
            if isinstance(item, IfNode):
                self._validate_block_types(item.then_block, module_name=module_name)
                self._validate_block_types(item.else_block, module_name=module_name)
                continue
            if isinstance(item, CaseNode):
                for branch in item.branches:
                    if branch.guard is not None:
                        self._validate_block_types(branch.guard, module_name=module_name)
                    self._validate_block_types(branch.body, module_name=module_name)

    def _validate_type_node(self, type_node: TypeNode, *, module_name: str) -> None:
        try:
            _validate_language_type_v1(
                type_node,
                declared_opaque_type_names=self._declared_opaque_type_names,
                resolve_import_category=lambda type_name: self._import_type_category(module_name, type_name),
            )
            validate_type_v1(type_node, forbid_quote=False)
        except HostABIError as error:
            self._raise_error(error.message, type_node.span.line, type_node.span.column, span=type_node.span)

    def _import_type_category(self, module_name: str, type_name: str) -> SymbolCategory | None:
        metadata = self._symbols.alias_metadata(module_name, type_name)
        if metadata is None:
            return None
        return metadata.category

    def _is_declared_opaque_type(self, type_node: TypeNode) -> bool:
        return type_node.name in self._declared_opaque_type_names and len(type_node.args) == 0

    def _check_word(self, word: WordDefNode) -> None:
        local_types = {parameter.name: parameter.type_node for parameter in word.signature.inputs}
        propagate_result_type = _single_result_output_type(word.signature.outputs)
        end_stack = self._check_block(word.body, [], local_types, propagate_result_type=propagate_result_type)
        expected_outputs = [parameter.type_node for parameter in word.signature.outputs]
        if not _same_stack(end_stack, expected_outputs):
            self._raise_error("word body does not match declared outputs", word.span.line, word.span.column, span=word.span)

        for nested_word in word.nested_words:
            self._check_word(nested_word)

    def _check_block(
        self,
        block: BlockNode,
        stack: list[TypeNode],
        local_types: dict[str, TypeNode],
        *,
        propagate_result_type: TypeNode | None,
    ) -> list[TypeNode]:
        current_stack = list(stack)
        for item in block.items:
            if isinstance(item, IdentifierNode):
                self._check_identifier(item, current_stack, local_types)
            elif isinstance(item, OperatorNode):
                self._check_operator(item, current_stack)
            elif isinstance(item, LiteralNode):
                current_stack.append(StackValue(_literal_type(item)))
            elif isinstance(item, TypedEmptyListNode):
                current_stack.append(StackValue(item.type_node, known_empty_list=True))
            elif isinstance(item, TypedEmptyMapNode):
                current_stack.append(StackValue(item.type_node))
            elif isinstance(item, IfNode):
                current_stack = self._check_if(
                    item,
                    current_stack,
                    local_types,
                    propagate_result_type=propagate_result_type,
                )
            elif isinstance(item, CaseNode):
                current_stack = self._check_case(
                    item,
                    current_stack,
                    local_types,
                    propagate_result_type=propagate_result_type,
                )
            elif isinstance(item, ListLiteralNode):
                current_stack.append(StackValue(self._check_list_literal(item, local_types)))
            elif isinstance(item, QuoteNode):
                current_stack = self._check_quote(item, current_stack)
            elif isinstance(item, ResultOkNode):
                self._check_result_ok(item, current_stack, propagate_result_type=propagate_result_type)
            elif isinstance(item, ResultErrNode):
                self._check_result_err(item, current_stack, propagate_result_type=propagate_result_type)
            elif isinstance(item, PropagateNode):
                self._check_propagate(item, current_stack, propagate_result_type=propagate_result_type)
            else:
                raise NotImplementedError(f"checking not implemented for {type(item).__name__}")
        return current_stack

    def _check_result_ok(
        self,
        node: ResultOkNode,
        stack,
        *,
        propagate_result_type: TypeNode | None,
    ) -> None:
        value_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
        if propagate_result_type is not None:
            result_parts = _extract_result_types(propagate_result_type)
            assert result_parts is not None
            expected_value_type, expected_error_type = result_parts
            if not _same_type(value_type, expected_value_type):
                self._raise_error("Ok! value type does not match frame Result value type", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_result_type(node.span, expected_value_type, expected_error_type)))
            return
        stack.append(StackValue(_result_type(node.span, value_type, _builtin_type("_UnknownError"))))

    def _check_result_err(
        self,
        node: ResultErrNode,
        stack,
        *,
        propagate_result_type: TypeNode | None,
    ) -> None:
        error_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
        if propagate_result_type is not None:
            result_parts = _extract_result_types(propagate_result_type)
            assert result_parts is not None
            expected_value_type, expected_error_type = result_parts
            if not _same_type(error_type, expected_error_type):
                self._raise_error("Err! error type does not match frame Result error type", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_result_type(node.span, expected_value_type, expected_error_type)))
            return
        stack.append(StackValue(_result_type(node.span, _builtin_type("_UnknownValue"), error_type)))

    def _check_propagate(
        self,
        node: PropagateNode,
        stack,
        *,
        propagate_result_type: TypeNode | None,
    ) -> None:
        result_input = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
        result_parts = _extract_result_types(result_input)
        if result_parts is None:
            self._raise_error("? expects Result<T,E>", node.span.line, node.span.column, span=node.span)
        value_type, error_type = result_parts

        if propagate_result_type is None:
            self._raise_error(
                "? requires frame output to be exactly one Result<T,E>",
                node.span.line,
                node.span.column,
                span=node.span,
            )
        frame_result_parts = _extract_result_types(propagate_result_type)
        assert frame_result_parts is not None
        _, frame_error_type = frame_result_parts
        if not _same_type(error_type, frame_error_type):
            self._raise_error(
                "? error type must exactly match frame Result error type",
                node.span.line,
                node.span.column,
                span=node.span,
            )
        stack.append(StackValue(value_type))

    def _check_identifier(
        self,
        node: IdentifierNode,
        stack: list[TypeNode],
        local_types: dict[str, TypeNode],
    ) -> None:
        qualified_name = node.resolution.qualified_name
        if qualified_name is not None and qualified_name.startswith("local:"):
            local_name = qualified_name.split(":", 1)[1]
            stack.append(StackValue(local_types[local_name]))
            return

        if node.resolution.owner_scope == "host":
            signature = node.resolution.signature_reference
            if signature is None:
                self._raise_error("unresolved host signature during checking", node.span.line, node.span.column, span=node.span)
            self._apply_signature(node.span.line, node.span.column, stack, signature.inputs, signature.outputs, span=node.span)
            return

        if node.resolution.owner_scope == "error-variant":
            variant_type = _error_variant_expression_type(node.name, node.span)
            if variant_type is None:
                self._raise_error("unresolved error variant during checking", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(variant_type))
            return

        symbol = node.resolution.resolved_symbol
        if symbol is None:
            self._raise_error("unresolved identifier during checking", node.span.line, node.span.column, span=node.span)

        if symbol.source is SymbolSource.BUILTIN:
            self._check_builtin(node, stack)
            return

        self._apply_signature(node.span.line, node.span.column, stack, symbol.signature.inputs, symbol.signature.outputs, span=node.span)

    def _check_builtin(self, node: IdentifierNode, stack: list[TypeNode]) -> None:
        if node.name in {"result.is-ok", "result.is-err"}:
            result_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _extract_result_types(result_type) is None:
                self._raise_error(f"{node.name} expects Result<T,E>", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_builtin_type("Bool")))
            return

        if node.name == "result.unwrap-or":
            fallback_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            result_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            result_parts = _extract_result_types(result_type)
            if result_parts is None:
                self._raise_error("result.unwrap-or expects Result<T,E> T", node.span.line, node.span.column, span=node.span)
            value_type, _ = result_parts
            if not _same_type(fallback_type, value_type):
                self._raise_error("result.unwrap-or fallback type must match Result value type", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(value_type))
            return

        if node.name == "list.len":
            collection_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _extract_list_item_type(collection_type) is None:
                self._raise_error("list.len expects List<T>", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_builtin_type("Int")))
            return

        if node.name == "list.is-empty":
            collection_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _extract_list_item_type(collection_type) is None:
                self._raise_error("list.is-empty expects List<T>", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_builtin_type("Bool")))
            return

        if node.name == "list.first":
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            if item_type is None:
                self._raise_error("list.first expects List<T>", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_result_type(node.span, item_type, _builtin_type("ListError"))))
            return

        if node.name == "list.last":
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            if item_type is None:
                self._raise_error("list.last expects List<T>", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_result_type(node.span, item_type, _builtin_type("ListError"))))
            return

        if node.name == "list.append":
            value_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            if item_type is None:
                self._raise_error("list.append expects List<T> T", node.span.line, node.span.column, span=node.span)
            if not _same_type(value_type, item_type):
                self._raise_error(
                    "list.append value type does not match list element type",
                    node.span.line,
                    node.span.column,
                    span=node.span,
                )
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(item_type,))))
            return

        if node.name == "list.reverse":
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            if item_type is None:
                self._raise_error("list.reverse expects List<T>", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(item_type,))))
            return

        if node.name == "list.concat":
            right_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            left_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            right_item_type = _extract_list_item_type(right_type)
            left_item_type = _extract_list_item_type(left_type)
            if right_item_type is None or left_item_type is None:
                self._raise_error("list.concat expects List<T> List<T>", node.span.line, node.span.column, span=node.span)
            if not _same_type(left_item_type, right_item_type):
                self._raise_error("list.concat expects matching list element types", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(left_item_type,))))
            return

        if node.name == "list.get":
            index_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            if item_type is None:
                self._raise_error("list.get expects List<T> Int", node.span.line, node.span.column, span=node.span)
            if not _is_named_type(index_type, "Int"):
                self._raise_error("list.get index must be Int", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_result_type(node.span, item_type, _builtin_type("ListError"))))
            return

        if node.name == "list.map":
            quote_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            quote_signature = _extract_quote_signature(quote_type)
            if item_type is None or quote_signature is None:
                self._raise_error("list.map expects List<T> (Quote|DirtyQuote)<{ | x:T -- y:U }>", node.span.line, node.span.column, span=node.span)
            if len(quote_signature.inputs) != 1 or len(quote_signature.outputs) != 1:
                self._raise_error("list.map quotation must have one input and one output", node.span.line, node.span.column, span=node.span)
            quote_input_type = quote_signature.inputs[0].type_node
            quote_output_type = quote_signature.outputs[0].type_node
            if not _same_type(quote_input_type, item_type):
                self._raise_error("list.map quotation input type does not match list element type", node.span.line, node.span.column, span=node.span)
            node.resolution.quote_effect = quote_signature.effect_kind
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(quote_output_type,))))
            return

        if node.name == "list.filter":
            quote_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            quote_signature = _extract_quote_signature(quote_type)
            if item_type is None or quote_signature is None:
                self._raise_error("list.filter expects List<T> (Quote|DirtyQuote)<{ | x:T -- keep:Bool }>", node.span.line, node.span.column, span=node.span)
            if len(quote_signature.inputs) != 1 or len(quote_signature.outputs) != 1:
                self._raise_error("list.filter quotation must have one input and one output", node.span.line, node.span.column, span=node.span)
            quote_input_type = quote_signature.inputs[0].type_node
            quote_output_type = quote_signature.outputs[0].type_node
            if not _same_type(quote_input_type, item_type):
                self._raise_error("list.filter quotation input type does not match list element type", node.span.line, node.span.column, span=node.span)
            if not _is_named_type(quote_output_type, "Bool"):
                self._raise_error("list.filter quotation output type must be Bool", node.span.line, node.span.column, span=node.span)
            node.resolution.quote_effect = quote_signature.effect_kind
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(item_type,))))
            return

        if node.name == "list.set":
            value_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            index_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            if item_type is None:
                self._raise_error("list.set expects List<T> Int T", node.span.line, node.span.column, span=node.span)
            if not _is_named_type(index_type, "Int"):
                self._raise_error("list.set index must be Int", node.span.line, node.span.column, span=node.span)
            if not _same_type(value_type, item_type):
                self._raise_error("list.set value type does not match list element type", node.span.line, node.span.column, span=node.span)
            stack.append(
                StackValue(
                    _result_type(
                        node.span,
                        TypeNode(span=node.span, name="List", args=(item_type,)),
                        _builtin_type("ListError"),
                    )
                )
            )
            return

        if node.name == "list.fold":
            quote_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            accumulator_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            list_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            item_type = _extract_list_item_type(list_type)
            quote_signature = _extract_quote_signature(quote_type)
            if item_type is None or quote_signature is None:
                self._raise_error("list.fold expects List<T> Acc (Quote|DirtyQuote)<{ | acc:Acc x:T -- out:Acc }>", node.span.line, node.span.column, span=node.span)
            if len(quote_signature.inputs) != 2 or len(quote_signature.outputs) != 1:
                self._raise_error("list.fold quotation must have two inputs and one output", node.span.line, node.span.column, span=node.span)
            if not _same_type(quote_signature.inputs[0].type_node, accumulator_type):
                self._raise_error("list.fold quotation accumulator type does not match init type", node.span.line, node.span.column, span=node.span)
            if not _same_type(quote_signature.inputs[1].type_node, item_type):
                self._raise_error("list.fold quotation item type does not match list element type", node.span.line, node.span.column, span=node.span)
            if not _same_type(quote_signature.outputs[0].type_node, accumulator_type):
                self._raise_error("list.fold quotation output type does not match accumulator type", node.span.line, node.span.column, span=node.span)
            node.resolution.quote_effect = quote_signature.effect_kind
            stack.append(StackValue(accumulator_type))
            return

        if node.name == "list.reduce":
            quote_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            list_value = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            list_type = list_value.type_node
            item_type = _extract_list_item_type(list_type)
            quote_signature = _extract_quote_signature(quote_type)
            if item_type is None or quote_signature is None:
                self._raise_error("list.reduce expects List<T> (Quote|DirtyQuote)<{ | a:T b:T -- c:T }>", node.span.line, node.span.column, span=node.span)
            if list_value.known_empty_list:
                self._raise_error("list.reduce cannot be applied to a provably empty list", node.span.line, node.span.column, span=node.span)
            if len(quote_signature.inputs) != 2 or len(quote_signature.outputs) != 1:
                self._raise_error("list.reduce quotation must have two inputs and one output", node.span.line, node.span.column, span=node.span)
            if not _same_type(quote_signature.inputs[0].type_node, item_type):
                self._raise_error("list.reduce first quotation input type does not match list element type", node.span.line, node.span.column, span=node.span)
            if not _same_type(quote_signature.inputs[1].type_node, item_type):
                self._raise_error("list.reduce second quotation input type does not match list element type", node.span.line, node.span.column, span=node.span)
            if not _same_type(quote_signature.outputs[0].type_node, item_type):
                self._raise_error("list.reduce quotation output type does not match list element type", node.span.line, node.span.column, span=node.span)
            node.resolution.quote_effect = quote_signature.effect_kind
            stack.append(StackValue(item_type))
            return

        if node.name == "map.len":
            collection_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _extract_map_types(collection_type) is None:
                self._raise_error("map.len expects Map<K,V>", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_builtin_type("Int")))
            return

        if node.name == "map.is-empty":
            collection_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _extract_map_types(collection_type) is None:
                self._raise_error("map.is-empty expects Map<K,V>", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_builtin_type("Bool")))
            return

        if node.name == "map.keys":
            map_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.keys expects Map<K,V>", node.span.line, node.span.column, span=node.span)
            expected_key_type, _ = map_parts
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(expected_key_type,))))
            return

        if node.name == "map.values":
            map_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.values expects Map<K,V>", node.span.line, node.span.column, span=node.span)
            _, expected_value_type = map_parts
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(expected_value_type,))))
            return

        if node.name == "map.contains":
            key_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.contains expects Map<K,V> K", node.span.line, node.span.column, span=node.span)
            expected_key_type, _ = map_parts
            if not _same_type(key_type, expected_key_type):
                self._raise_error("map.contains key type does not match map key type", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_builtin_type("Bool")))
            return

        if node.name == "map.get":
            key_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.get expects Map<K,V> K", node.span.line, node.span.column, span=node.span)
            expected_key_type, value_type = map_parts
            if not _same_type(key_type, expected_key_type):
                self._raise_error("map.get key type does not match map key type", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_result_type(node.span, value_type, _builtin_type("MapError"))))
            return

        if node.name == "map.set":
            value_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            key_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.set expects Map<K,V> K V", node.span.line, node.span.column, span=node.span)
            expected_key_type, expected_value_type = map_parts
            if not _same_type(key_type, expected_key_type):
                self._raise_error("map.set key type does not match map key type", node.span.line, node.span.column, span=node.span)
            if not _same_type(value_type, expected_value_type):
                self._raise_error("map.set value type does not match map value type", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(TypeNode(span=node.span, name="Map", args=(expected_key_type, expected_value_type))))
            return

        if node.name == "map.remove":
            key_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.remove expects Map<K,V> K", node.span.line, node.span.column, span=node.span)
            expected_key_type, value_type = map_parts
            if not _same_type(key_type, expected_key_type):
                self._raise_error("map.remove key type does not match map key type", node.span.line, node.span.column, span=node.span)
            stack.append(StackValue(_result_type(node.span, TypeNode(span=node.span, name="Map", args=(expected_key_type, value_type)), _builtin_type("MapError"))))
            return

        raise NotImplementedError("builtin checking is not implemented")

    def _check_operator(self, node: OperatorNode, stack: list[TypeNode]) -> None:
        if node.operator == "call":
            quote_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            quote_signature = _extract_quote_signature(quote_type)
            if quote_signature is None:
                self._raise_error("call expects Quote<{ ... }> or DirtyQuote<{ ... }>", node.span.line, node.span.column, span=node.span)
            for parameter in reversed(quote_signature.inputs):
                actual = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
                if not _same_type(actual, parameter.type_node):
                    self._raise_error("call input types do not match quotation inputs", node.span.line, node.span.column, span=node.span)
            for parameter in quote_signature.outputs:
                stack.append(StackValue(parameter.type_node))
            node.resolution.quote_effect = quote_signature.effect_kind
            return

        if node.operator == "drop":
            self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            return

        if node.operator == "dup":
            value = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            stack.append(value)
            stack.append(value)
            return

        if node.operator == "swap":
            right = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            left = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            stack.append(right)
            stack.append(left)
            return

        if node.operator == "over":
            right = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            left = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            stack.append(left)
            stack.append(right)
            stack.append(left)
            return

        if node.operator == "rot":
            third = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            second = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            first = self._pop_value(stack, node.span.line, node.span.column, span=node.span)
            stack.append(second)
            stack.append(third)
            stack.append(first)
            return

        if node.operator in {"+", "-", "*", "div", "mod"}:
            right = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            left = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _is_named_type(left, "Int") and _is_named_type(right, "Int"):
                stack.append(StackValue(_builtin_type("Int")))
                return
            self._raise_error("invalid arithmetic operand types", node.span.line, node.span.column, span=node.span)

        if node.operator in {"+.", "-.", "*.", "/."}:
            right = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            left = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _is_named_type(left, "Float") and _is_named_type(right, "Float"):
                stack.append(StackValue(_builtin_type("Float")))
                return
            self._raise_error("invalid arithmetic operand types", node.span.line, node.span.column, span=node.span)

        if node.operator in {"<", "<=", ">", ">="}:
            right = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            left = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if (
                _is_named_type(left, "Int") and _is_named_type(right, "Int")
            ) or (
                _is_named_type(left, "Float") and _is_named_type(right, "Float")
            ):
                stack.append(StackValue(_builtin_type("Bool")))
                return
            self._raise_error("invalid comparison operand types", node.span.line, node.span.column, span=node.span)

        if node.operator in {"=", "!="}:
            right = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            left = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _same_type(left, right):
                if self._is_declared_opaque_type(left):
                    self._raise_error("equality is not supported for host opaque types", node.span.line, node.span.column, span=node.span)
                stack.append(StackValue(_builtin_type("Bool")))
                return
            self._raise_error("invalid equality operand types", node.span.line, node.span.column, span=node.span)

        if node.operator in {"and", "or"}:
            right = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            left = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _is_named_type(left, "Bool") and _is_named_type(right, "Bool"):
                stack.append(StackValue(_builtin_type("Bool")))
                return
            self._raise_error("invalid boolean operand types", node.span.line, node.span.column, span=node.span)

        if node.operator == "not":
            value = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
            if _is_named_type(value, "Bool"):
                stack.append(StackValue(_builtin_type("Bool")))
                return
            self._raise_error("invalid boolean operand types", node.span.line, node.span.column, span=node.span)

        raise NotImplementedError(f"operator checking not implemented for {node.operator}")

    def _check_if(
        self,
        node: IfNode,
        stack: list[TypeNode],
        local_types: dict[str, TypeNode],
        *,
        propagate_result_type: TypeNode | None,
    ) -> list[TypeNode]:
        condition_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
        if not _is_named_type(condition_type, "Bool"):
            self._raise_error("if condition must be Bool", node.span.line, node.span.column, span=node.span)

        base_stack = list(stack)
        then_stack = self._check_block(
            node.then_block,
            list(base_stack),
            local_types,
            propagate_result_type=propagate_result_type,
        )
        else_stack = self._check_block(
            node.else_block,
            list(base_stack),
            local_types,
            propagate_result_type=propagate_result_type,
        )
        if not _same_stack(then_stack, else_stack):
            self._raise_error("if branches have incompatible stack effects", node.span.line, node.span.column, span=node.span)
        return then_stack

    def _check_case(
        self,
        node: CaseNode,
        stack: list[TypeNode],
        local_types: dict[str, TypeNode],
        *,
        propagate_result_type: TypeNode | None,
    ) -> list[TypeNode]:
        scrutinee_type = self._pop_type(stack, node.span.line, node.span.column, span=node.span)
        base_stack = list(stack)
        branch_stacks: list[list[TypeNode]] = []

        for branch in node.branches:
            branch_locals = dict(local_types)
            self._bind_case_pattern(branch.pattern, scrutinee_type, branch_locals)
            if branch.guard is not None:
                self._check_case_guard(
                    branch.guard,
                    branch_locals,
                    propagate_result_type=propagate_result_type,
                )
            branch_stack = self._check_block(
                branch.body,
                list(base_stack),
                branch_locals,
                propagate_result_type=propagate_result_type,
            )
            branch_stacks.append(branch_stack)

        if not branch_stacks:
            self._raise_error("case must have at least one branch", node.span.line, node.span.column, span=node.span)

        expected_stack = branch_stacks[0]
        for branch_stack in branch_stacks[1:]:
            if not _same_stack(branch_stack, expected_stack):
                self._raise_error(
                    "case branches have incompatible stack effects",
                    node.span.line,
                    node.span.column,
                    span=node.span,
                )
        if not _is_case_exhaustive(node, scrutinee_type):
            self._raise_error("case is not exhaustive", node.span.line, node.span.column, span=node.span)
        return expected_stack

    def _check_case_guard(
        self,
        guard: BlockNode,
        local_types: dict[str, TypeNode],
        *,
        propagate_result_type: TypeNode | None,
    ) -> None:
        if self._contains_propagate(guard):
            self._raise_error(
                "case guard cannot contain ?",
                guard.span.line,
                guard.span.column,
                span=guard.span,
            )

        try:
            guard_stack = self._check_block(
                guard,
                [],
                local_types,
                propagate_result_type=propagate_result_type,
            )
        except CheckerError as error:
            if error.message == "insufficient stack":
                self._raise_error(
                    "case guard must not consume preexisting stack values",
                    error.line,
                    error.column,
                    span=error.diagnostic.span,
                )
            raise

        if len(guard_stack) != 1:
            self._raise_error(
                "case guard must produce exactly one Bool",
                guard.span.line,
                guard.span.column,
                span=guard.span,
            )
        if not _is_named_type(_stack_item_type(guard_stack[0]), "Bool"):
            self._raise_error(
                "case guard must produce Bool",
                guard.span.line,
                guard.span.column,
                span=guard.span,
            )

    def _contains_propagate(self, block: BlockNode) -> bool:
        for item in block.items:
            if isinstance(item, PropagateNode):
                return True
            if isinstance(item, IfNode):
                if self._contains_propagate(item.then_block) or self._contains_propagate(item.else_block):
                    return True
                continue
            if isinstance(item, CaseNode):
                for branch in item.branches:
                    if branch.guard is not None and self._contains_propagate(branch.guard):
                        return True
                    if self._contains_propagate(branch.body):
                        return True
                continue
            if isinstance(item, QuoteNode):
                if self._contains_propagate(item.body):
                    return True
                continue
            if isinstance(item, ListLiteralNode):
                if self._contains_propagate(BlockNode(span=item.span, items=item.elements)):
                    return True
        return False

    def _bind_case_pattern(
        self,
        pattern,
        scrutinee_type: TypeNode,
        local_types: dict[str, TypeNode],
    ) -> None:
        if pattern.kind is PatternKind.WILDCARD:
            return

        if pattern.kind is PatternKind.LITERAL:
            pattern_type = _pattern_literal_type(pattern.value)
            if not _same_type(scrutinee_type, pattern_type):
                self._raise_error(
                    "case pattern does not match scrutinee type",
                    pattern.span.line,
                    pattern.span.column,
                    span=pattern.span,
                )
            return

        if pattern.kind is PatternKind.NAME:
            if pattern.value not in {"MissingKey", "OutOfBounds"}:
                self._raise_error("unsupported case pattern", pattern.span.line, pattern.span.column, span=pattern.span)
            if not _is_valid_closed_variant_pattern(scrutinee_type, pattern.value):
                self._raise_error(
                    "case pattern does not match scrutinee type",
                    pattern.span.line,
                    pattern.span.column,
                    span=pattern.span,
                )
            return

        if pattern.kind in {PatternKind.OK, PatternKind.ERR}:
            if scrutinee_type.name != "Result" or len(scrutinee_type.args) != 2:
                self._raise_error(
                    "Ok/Err pattern requires Result scrutinee",
                    pattern.span.line,
                    pattern.span.column,
                    span=pattern.span,
                )
            if pattern.kind is PatternKind.ERR and pattern.value is not None:
                if not _is_valid_result_error_variant(scrutinee_type, pattern.value):
                    self._raise_error(
                        "case pattern does not match scrutinee type",
                        pattern.span.line,
                        pattern.span.column,
                        span=pattern.span,
                    )
            if pattern.binding is None:
                return
            branch_type = scrutinee_type.args[0] if pattern.kind is PatternKind.OK else scrutinee_type.args[1]
            if not isinstance(branch_type, TypeNode):
                self._raise_error("unsupported Result type argument", pattern.span.line, pattern.span.column, span=pattern.span)
            local_types[pattern.binding] = branch_type
            return

        self._raise_error("unsupported case pattern", pattern.span.line, pattern.span.column, span=pattern.span)

    def _check_quote(self, node: QuoteNode, stack: list[TypeNode]) -> list[TypeNode]:
        current_stack = list(stack)
        for parameter in reversed(node.captures):
            actual = self._pop_type(current_stack, node.span.line, node.span.column, span=node.span)
            if not _same_type(actual, parameter.type_node):
                self._raise_error("quotation capture types do not match", node.span.line, node.span.column, span=node.span)

        quote_locals = {parameter.name: parameter.type_node for parameter in node.captures}
        quote_locals.update({parameter.name: parameter.type_node for parameter in node.inputs})
        quote_propagate_result_type = _single_result_output_type(node.outputs)
        quote_end_stack = self._check_block(
            node.body,
            [],
            quote_locals,
            propagate_result_type=quote_propagate_result_type,
        )
        expected_outputs = [parameter.type_node for parameter in node.outputs]
        if not _same_stack(quote_end_stack, expected_outputs):
            self._raise_error("quotation body does not match declared outputs", node.span.line, node.span.column, span=node.span)
        quote_effect = self._infer_quote_effect_for_typecheck(node.body)
        node.resolution.quote_effect = quote_effect

        quote_type = TypeNode(
            span=node.span,
            name="Quote",
            args=(
                QuoteTypeNode(
                    span=node.span,
                    effect_kind=quote_effect,
                    captures=node.captures,
                    inputs=node.inputs,
                    outputs=node.outputs,
                ),
            ),
        )
        current_stack.append(StackValue(quote_type))
        return current_stack

    def _check_list_literal(
        self,
        node: ListLiteralNode,
        local_types: dict[str, TypeNode],
    ) -> TypeNode:
        element_types = [self._check_list_element_value(element, local_types) for element in node.elements]
        first_type = element_types[0]
        for element_type in element_types[1:]:
            if not _same_type(first_type, element_type):
                self._raise_error("list literal elements must have the same type", node.span.line, node.span.column, span=node.span)
        return TypeNode(span=node.span, name="List", args=(first_type,))

    def _check_list_element_value(
        self,
        element,
        local_types: dict[str, TypeNode],
    ) -> TypeNode:
        stack = self._check_block(
            BlockNode(span=element.span, items=(element,)),
            [],
            local_types,
            propagate_result_type=None,
        )
        if len(stack) != 1:
            self._raise_error("list literal element must produce exactly one value", element.span.line, element.span.column, span=element.span)
        return stack[0].type_node

    def _apply_signature(
        self,
        line: int,
        column: int,
        stack: list[TypeNode],
        inputs,
        outputs,
        *,
        span: SourceSpan | None = None,
    ) -> None:
        for parameter in reversed(inputs):
            actual = self._pop_type(stack, line, column, span=span)
            if not _same_type(actual, parameter.type_node):
                self._raise_error("type mismatch in word call", line, column, span=span)
        for parameter in outputs:
            stack.append(StackValue(parameter.type_node))

    def _pop_value(self, stack, line: int, column: int, *, span: SourceSpan | None = None) -> StackValue:
        if not stack:
            self._raise_error("insufficient stack", line, column, span=span)
        return stack.pop()

    def _pop_type(self, stack, line: int, column: int, *, span: SourceSpan | None = None) -> TypeNode:
        return self._pop_value(stack, line, column, span=span).type_node

    def _raise_error(
        self,
        message: str,
        line: int,
        column: int,
        *,
        span: SourceSpan | None = None,
        suggestion: str | None = None,
    ) -> None:
        resolved_span = span if span is not None else SourceSpan(line=line, column=column, offset=0)
        raise CheckerError(
            message=message,
            line=line,
            column=column,
            code=_checker_code_for_message(message),
            span=resolved_span,
            suggestion=suggestion,
        )

    def _infer_quote_effect_for_typecheck(self, block: BlockNode) -> QuoteEffect:
        for item in block.items:
            if self._item_introduces_dirty_quote_effect_for_typecheck(item):
                return QuoteEffect.DIRTY
        return QuoteEffect.PURE

    def _item_introduces_dirty_quote_effect_for_typecheck(self, item) -> bool:
        if isinstance(item, IdentifierNode):
            if item.resolution.owner_scope == "host":
                return item.resolution.host_effect is HostEffect.DIRTY
            if item.name in {"list.map", "list.filter", "list.fold", "list.reduce"}:
                return item.resolution.quote_effect is QuoteEffect.DIRTY
            symbol = item.resolution.resolved_symbol
            if isinstance(symbol, WordSymbol) and symbol.source is SymbolSource.USER:
                return bool(item.resolution.declared_dirty)
            return False
        if isinstance(item, OperatorNode):
            return item.operator == "call" and item.resolution.quote_effect is QuoteEffect.DIRTY
        if isinstance(item, QuoteNode):
            return (
                item.resolution.quote_effect is QuoteEffect.DIRTY
                or self._infer_quote_effect_for_typecheck(item.body) is QuoteEffect.DIRTY
            )
        if isinstance(item, IfNode):
            return (
                self._infer_quote_effect_for_typecheck(item.then_block) is QuoteEffect.DIRTY
                or self._infer_quote_effect_for_typecheck(item.else_block) is QuoteEffect.DIRTY
            )
        if isinstance(item, CaseNode):
            for branch in item.branches:
                if branch.guard is not None and self._infer_quote_effect_for_typecheck(branch.guard) is QuoteEffect.DIRTY:
                    return True
                if self._infer_quote_effect_for_typecheck(branch.body) is QuoteEffect.DIRTY:
                    return True
            return False
        if isinstance(item, ListLiteralNode):
            for element in item.elements:
                if self._item_introduces_dirty_quote_effect_for_typecheck(element):
                    return True
            return False
        return False

    def _analyze_effects(self, program: ProgramNode) -> EffectAnalysisResult:
        words = self._collect_words(program)
        word_order = [qualified_name for qualified_name, _ in words]
        declared_dirty_by_word = {qualified_name: word.is_dirty_annotation for qualified_name, word in words}
        spans_by_word = {
            qualified_name: word.span
            for qualified_name, word in words
        }
        known_words = set(word_order)
        word_node_by_name = {qualified_name: f"word:{qualified_name}" for qualified_name in word_order}
        node_order = [word_node_by_name[name] for name in word_order]
        graph: dict[str, set[str]] = {node: set() for node in node_order}
        direct_dirty_source_by_node: dict[str, bool] = {node: False for node in node_order}
        quote_nodes: dict[str, QuoteNode] = {}
        quote_site_counter = 0
        calls_by_word: dict[str, list[_CallEdge]] = {qualified_name: [] for qualified_name in word_order}

        def ensure_node(node_id: str) -> None:
            if node_id in graph:
                return
            graph[node_id] = set()
            direct_dirty_source_by_node[node_id] = False
            node_order.append(node_id)

        def add_edge(source: str, target: str) -> None:
            ensure_node(source)
            ensure_node(target)
            graph[source].add(target)

        def mark_direct_dirty(node_id: str) -> None:
            ensure_node(node_id)
            direct_dirty_source_by_node[node_id] = True

        def classify_identifier(
            identifier: IdentifierNode,
            *,
            source_node: str,
            owner_word_name: str,
            is_owner_word_frame: bool,
        ) -> None:
            if identifier.resolution.owner_scope == "host":
                if identifier.resolution.host_effect is HostEffect.DIRTY:
                    mark_direct_dirty(source_node)
                return
            if (
                identifier.name in {"list.map", "list.filter", "list.fold", "list.reduce"}
                and identifier.resolution.quote_effect is QuoteEffect.DIRTY
            ):
                mark_direct_dirty(source_node)
                return
            symbol = identifier.resolution.resolved_symbol
            if not isinstance(symbol, WordSymbol):
                return
            if symbol.source is not SymbolSource.USER:
                return
            callee_name = _symbol_word_identity(symbol)
            if callee_name is None:
                return
            if callee_name not in known_words:
                return
            add_edge(source_node, word_node_by_name[callee_name])
            if is_owner_word_frame:
                calls_by_word[owner_word_name].append(
                    _CallEdge(
                        caller=owner_word_name,
                        callee=callee_name,
                        line=identifier.span.line,
                        column=identifier.span.column,
                        span=identifier.span,
                    )
                )

        def walk_block(
            block: BlockNode,
            *,
            source_node: str,
            owner_word_name: str,
            is_owner_word_frame: bool,
        ) -> None:
            nonlocal quote_site_counter
            for item in block.items:
                if isinstance(item, IdentifierNode):
                    classify_identifier(
                        item,
                        source_node=source_node,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=is_owner_word_frame,
                    )
                    continue
                if isinstance(item, OperatorNode):
                    if item.operator == "call" and item.resolution.quote_effect is QuoteEffect.DIRTY:
                        mark_direct_dirty(source_node)
                    continue
                if isinstance(item, IfNode):
                    walk_block(
                        item.then_block,
                        source_node=source_node,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=is_owner_word_frame,
                    )
                    walk_block(
                        item.else_block,
                        source_node=source_node,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=is_owner_word_frame,
                    )
                    continue
                if isinstance(item, CaseNode):
                    for branch in item.branches:
                        if branch.guard is not None:
                            walk_block(
                                branch.guard,
                                source_node=source_node,
                                owner_word_name=owner_word_name,
                                is_owner_word_frame=is_owner_word_frame,
                            )
                        walk_block(
                            branch.body,
                            source_node=source_node,
                            owner_word_name=owner_word_name,
                            is_owner_word_frame=is_owner_word_frame,
                        )
                    continue
                if isinstance(item, ListLiteralNode):
                    walk_list_literal(
                        item,
                        source_node=source_node,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=is_owner_word_frame,
                    )
                    continue
                if isinstance(item, QuoteNode):
                    quote_site_counter += 1
                    quote_node_id = f"quote:{owner_word_name}:{quote_site_counter}"
                    quote_nodes[quote_node_id] = item
                    add_edge(source_node, quote_node_id)
                    walk_block(
                        item.body,
                        source_node=quote_node_id,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=False,
                    )

        def walk_list_literal(
            list_literal: ListLiteralNode,
            *,
            source_node: str,
            owner_word_name: str,
            is_owner_word_frame: bool,
        ) -> None:
            nonlocal quote_site_counter
            for element in list_literal.elements:
                if isinstance(element, IdentifierNode):
                    classify_identifier(
                        element,
                        source_node=source_node,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=is_owner_word_frame,
                    )
                    continue
                if isinstance(element, OperatorNode):
                    if element.operator == "call" and element.resolution.quote_effect is QuoteEffect.DIRTY:
                        mark_direct_dirty(source_node)
                    continue
                if isinstance(element, IfNode):
                    walk_block(
                        element.then_block,
                        source_node=source_node,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=is_owner_word_frame,
                    )
                    walk_block(
                        element.else_block,
                        source_node=source_node,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=is_owner_word_frame,
                    )
                    continue
                if isinstance(element, CaseNode):
                    for branch in element.branches:
                        if branch.guard is not None:
                            walk_block(
                                branch.guard,
                                source_node=source_node,
                                owner_word_name=owner_word_name,
                                is_owner_word_frame=is_owner_word_frame,
                            )
                        walk_block(
                            branch.body,
                            source_node=source_node,
                            owner_word_name=owner_word_name,
                            is_owner_word_frame=is_owner_word_frame,
                        )
                    continue
                if isinstance(element, ListLiteralNode):
                    walk_list_literal(
                        element,
                        source_node=source_node,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=is_owner_word_frame,
                    )
                    continue
                if isinstance(element, QuoteNode):
                    quote_site_counter += 1
                    quote_node_id = f"quote:{owner_word_name}:{quote_site_counter}"
                    quote_nodes[quote_node_id] = element
                    add_edge(source_node, quote_node_id)
                    walk_block(
                        element.body,
                        source_node=quote_node_id,
                        owner_word_name=owner_word_name,
                        is_owner_word_frame=False,
                    )

        for qualified_name, word in words:
            walk_block(
                word.body,
                source_node=word_node_by_name[qualified_name],
                owner_word_name=qualified_name,
                is_owner_word_frame=True,
            )

        components, component_for_node = _compute_sccs(graph, node_order)
        reverse_component_edges: dict[int, set[int]] = {component_id: set() for component_id in range(len(components))}
        direct_dirty_components: set[int] = set()

        for component_id, component_nodes in enumerate(components):
            if any(direct_dirty_source_by_node[node_id] for node_id in component_nodes):
                direct_dirty_components.add(component_id)

        for caller_node, callees in graph.items():
            caller_component = component_for_node[caller_node]
            for callee_node in callees:
                callee_component = component_for_node[callee_node]
                reverse_component_edges[callee_component].add(caller_component)

        dirty_components = set(direct_dirty_components)
        queue: deque[int] = deque(sorted(direct_dirty_components))
        while queue:
            dirty_component = queue.popleft()
            for caller_component in sorted(reverse_component_edges[dirty_component]):
                if caller_component in dirty_components:
                    continue
                dirty_components.add(caller_component)
                queue.append(caller_component)

        inferred_dirty_by_node = {
            node_id: component_for_node[node_id] in dirty_components
            for node_id in node_order
        }
        for quote_node_id, quote_node in quote_nodes.items():
            quote_node.resolution.quote_effect = (
                QuoteEffect.DIRTY if inferred_dirty_by_node[quote_node_id] else QuoteEffect.PURE
            )

        effects = {}
        for word_name in word_order:
            node_id = word_node_by_name[word_name]
            effects[word_name] = WordEffectInfo(
                declared_dirty=declared_dirty_by_word[word_name],
                inferred_dirty=inferred_dirty_by_node[node_id],
                direct_dirty_source=direct_dirty_source_by_node[node_id],
            )
        frozen_calls_by_word = {
            word_name: tuple(calls_by_word[word_name])
            for word_name in word_order
        }
        return EffectAnalysisResult(
            effects=effects,
            calls_by_word=frozen_calls_by_word,
            word_order=tuple(word_order),
            word_spans=spans_by_word,
        )

    def _collect_words(self, program: ProgramNode) -> list[tuple[str, WordDefNode]]:
        collected: list[tuple[str, WordDefNode]] = []
        for declaration in program.declarations:
            if not isinstance(declaration, ModuleDeclaration):
                continue
            module_name = ".".join(declaration.name.parts)
            for item in declaration.items:
                if isinstance(item, WordDefNode):
                    self._collect_nested_words(
                        item,
                        module_name=module_name,
                        owner=None,
                        out=collected,
                    )
        return collected

    def _collect_nested_words(
        self,
        word: WordDefNode,
        *,
        module_name: str,
        owner: str | None,
        out: list[tuple[str, WordDefNode]],
    ) -> None:
        owner_qualified_name = _qualified_name(owner, word.name)
        out.append((_word_identity(module_name, owner_qualified_name), word))
        for nested_word in word.nested_words:
            self._collect_nested_words(
                nested_word,
                module_name=module_name,
                owner=owner_qualified_name,
                out=out,
            )

    def _mark_direct_self_tail_calls(self, program: ProgramNode) -> None:
        for qualified_name, word in self._collect_words(program):
            self._clear_tail_self_call_marks(word.body)
            self._mark_tail_self_calls_in_block(
                word.body,
                current_word_name=qualified_name,
                tail_position=True,
            )

    def _clear_tail_self_call_marks(self, block: BlockNode) -> None:
        for item in block.items:
            if isinstance(item, IdentifierNode):
                item.resolution.is_self_tail_call = False
                continue
            if isinstance(item, IfNode):
                self._clear_tail_self_call_marks(item.then_block)
                self._clear_tail_self_call_marks(item.else_block)
                continue
            if isinstance(item, CaseNode):
                for branch in item.branches:
                    if branch.guard is not None:
                        self._clear_tail_self_call_marks(branch.guard)
                    self._clear_tail_self_call_marks(branch.body)
                continue
            if isinstance(item, QuoteNode):
                self._clear_tail_self_call_marks(item.body)
                continue
            if isinstance(item, ListLiteralNode):
                self._clear_tail_self_call_marks(
                    BlockNode(span=item.span, items=item.elements)
                )

    def _mark_tail_self_calls_in_block(
        self,
        block: BlockNode,
        *,
        current_word_name: str,
        tail_position: bool,
    ) -> None:
        if not block.items:
            return

        for item in block.items[:-1]:
            self._mark_tail_self_calls_in_item(
                item,
                current_word_name=current_word_name,
                tail_position=False,
            )
        self._mark_tail_self_calls_in_item(
            block.items[-1],
            current_word_name=current_word_name,
            tail_position=tail_position,
        )

    def _mark_tail_self_calls_in_item(
        self,
        item,
        *,
        current_word_name: str,
        tail_position: bool,
    ) -> None:
        if isinstance(item, IdentifierNode):
            item.resolution.is_self_tail_call = (
                tail_position and self._is_direct_self_call(item, current_word_name)
            )
            return

        if isinstance(item, IfNode):
            self._mark_tail_self_calls_in_block(
                item.then_block,
                current_word_name=current_word_name,
                tail_position=tail_position,
            )
            self._mark_tail_self_calls_in_block(
                item.else_block,
                current_word_name=current_word_name,
                tail_position=tail_position,
            )
            return

        if isinstance(item, CaseNode):
            for branch in item.branches:
                if branch.guard is not None:
                    self._mark_tail_self_calls_in_block(
                        branch.guard,
                        current_word_name=current_word_name,
                        tail_position=False,
                    )
                self._mark_tail_self_calls_in_block(
                    branch.body,
                    current_word_name=current_word_name,
                    tail_position=tail_position,
                )

    def _is_direct_self_call(self, node: IdentifierNode, current_word_name: str) -> bool:
        symbol = node.resolution.resolved_symbol
        symbol_name = _symbol_word_identity(symbol) if isinstance(symbol, WordSymbol) else None
        return (
            isinstance(symbol, WordSymbol)
            and symbol.source is SymbolSource.USER
            and symbol_name == current_word_name
        )

    def _validate_quote_effect_restrictions(self, program: ProgramNode, analysis: EffectAnalysisResult) -> None:
        words = self._collect_words(program)
        word_nodes_by_name = {qualified_name: word for qualified_name, word in words}

        for word_name in analysis.word_order:
            effect = analysis.effects[word_name]
            if effect.declared_dirty:
                continue
            word_node = word_nodes_by_name.get(word_name)
            if word_node is None:
                continue
            violation = self._find_dirty_quote_usage(word_node.body)
            if violation is None:
                continue
            message, line, column, span = violation
            self._raise_error(message, line, column, span=span)

    def _validate_case_guard_purity(self, program: ProgramNode, analysis: EffectAnalysisResult) -> None:
        for _, word in self._collect_words(program):
            violation = self._find_dirty_case_guard(word.body, analysis)
            if violation is None:
                continue
            message, line, column, span = violation
            self._raise_error(message, line, column, span=span)

    def _find_dirty_case_guard(
        self,
        block: BlockNode,
        analysis: EffectAnalysisResult,
    ) -> tuple[str, int, int, SourceSpan] | None:
        for item in block.items:
            if isinstance(item, CaseNode):
                for branch in item.branches:
                    if branch.guard is not None:
                        violation = self._find_dirty_call_in_guard(branch.guard, analysis)
                        if violation is not None:
                            return violation
                        nested = self._find_dirty_case_guard(branch.guard, analysis)
                        if nested is not None:
                            return nested
                    nested = self._find_dirty_case_guard(branch.body, analysis)
                    if nested is not None:
                        return nested
                continue
            if isinstance(item, IfNode):
                nested = self._find_dirty_case_guard(item.then_block, analysis)
                if nested is not None:
                    return nested
                nested = self._find_dirty_case_guard(item.else_block, analysis)
                if nested is not None:
                    return nested
                continue
            if isinstance(item, QuoteNode):
                nested = self._find_dirty_case_guard(item.body, analysis)
                if nested is not None:
                    return nested
                continue
            if isinstance(item, ListLiteralNode):
                nested = self._find_dirty_case_guard(
                    BlockNode(span=item.span, items=item.elements),
                    analysis,
                )
                if nested is not None:
                    return nested
        return None

    def _find_dirty_call_in_guard(
        self,
        block: BlockNode,
        analysis: EffectAnalysisResult,
    ) -> tuple[str, int, int, SourceSpan] | None:
        for item in block.items:
            if isinstance(item, IdentifierNode):
                if item.resolution.owner_scope == "host" and item.resolution.host_effect is HostEffect.DIRTY:
                    return ("case guard cannot call dirty code", item.span.line, item.span.column, item.span)
                if (
                    item.name in {"list.map", "list.filter", "list.fold", "list.reduce"}
                    and item.resolution.quote_effect is QuoteEffect.DIRTY
                ):
                    return ("case guard cannot call dirty code", item.span.line, item.span.column, item.span)
                symbol = item.resolution.resolved_symbol
                if isinstance(symbol, WordSymbol) and symbol.source is SymbolSource.USER:
                    callee_name = _symbol_word_identity(symbol)
                    if callee_name is None:
                        continue
                    callee_effect = analysis.effects.get(callee_name)
                    if callee_effect is not None and callee_effect.inferred_dirty:
                        return ("case guard cannot call dirty code", item.span.line, item.span.column, item.span)
                continue
            if isinstance(item, OperatorNode):
                if item.operator == "call" and item.resolution.quote_effect is QuoteEffect.DIRTY:
                    return ("case guard cannot call dirty code", item.span.line, item.span.column, item.span)
                continue
            if isinstance(item, IfNode):
                nested = self._find_dirty_call_in_guard(item.then_block, analysis)
                if nested is not None:
                    return nested
                nested = self._find_dirty_call_in_guard(item.else_block, analysis)
                if nested is not None:
                    return nested
                continue
            if isinstance(item, CaseNode):
                for branch in item.branches:
                    if branch.guard is not None:
                        nested = self._find_dirty_call_in_guard(branch.guard, analysis)
                        if nested is not None:
                            return nested
                    nested = self._find_dirty_call_in_guard(branch.body, analysis)
                    if nested is not None:
                        return nested
                continue
            if isinstance(item, QuoteNode):
                nested = self._find_dirty_call_in_guard(item.body, analysis)
                if nested is not None:
                    return nested
                continue
            if isinstance(item, ListLiteralNode):
                nested = self._find_dirty_call_in_guard(
                    BlockNode(span=item.span, items=item.elements),
                    analysis,
                )
                if nested is not None:
                    return nested
        return None

    def _find_dirty_quote_usage(self, block: BlockNode) -> tuple[str, int, int, SourceSpan] | None:
        for item in block.items:
            if isinstance(item, QuoteNode):
                if item.resolution.quote_effect is QuoteEffect.DIRTY:
                    return (
                        "pure frame cannot construct DirtyQuote",
                        item.span.line,
                        item.span.column,
                        item.span,
                    )
                nested = self._find_dirty_quote_usage(item.body)
                if nested is not None:
                    return nested
                continue
            if isinstance(item, OperatorNode):
                if item.operator == "call" and item.resolution.quote_effect is QuoteEffect.DIRTY:
                    return (
                        "pure frame cannot call DirtyQuote",
                        item.span.line,
                        item.span.column,
                        item.span,
                    )
                continue
            if isinstance(item, IdentifierNode):
                if (
                    item.name in {"list.map", "list.filter", "list.fold", "list.reduce"}
                    and item.resolution.quote_effect is QuoteEffect.DIRTY
                ):
                    return (
                        f"pure frame cannot pass DirtyQuote to {item.name}",
                        item.span.line,
                        item.span.column,
                        item.span,
                    )
                continue
            if isinstance(item, IfNode):
                nested = self._find_dirty_quote_usage(item.then_block)
                if nested is not None:
                    return nested
                nested = self._find_dirty_quote_usage(item.else_block)
                if nested is not None:
                    return nested
                continue
            if isinstance(item, CaseNode):
                for branch in item.branches:
                    if branch.guard is not None:
                        nested = self._find_dirty_quote_usage(branch.guard)
                        if nested is not None:
                            return nested
                    nested = self._find_dirty_quote_usage(branch.body)
                    if nested is not None:
                        return nested
                continue
            if isinstance(item, ListLiteralNode):
                nested = self._find_dirty_quote_usage(BlockNode(span=item.span, items=item.elements))
                if nested is not None:
                    return nested
        return None

    def _validate_pure_to_dirty_calls(self, analysis: EffectAnalysisResult) -> None:
        for caller in analysis.word_order:
            caller_effect = analysis.effects[caller]
            if caller_effect.declared_dirty:
                continue
            for edge in analysis.calls_by_word[caller]:
                callee_effect = analysis.effects.get(edge.callee)
                if callee_effect is None:
                    continue
                if callee_effect.inferred_dirty:
                    self._raise_error(
                        f"pure word '{caller}' cannot call dirty word '{edge.callee}'",
                        edge.line,
                        edge.column,
                        span=edge.span,
                    )

    def _validate_effect_annotations(self, analysis: EffectAnalysisResult) -> None:
        for word_name in analysis.word_order:
            effect = analysis.effects[word_name]
            span = analysis.word_spans[word_name]
            line, column = span.line, span.column
            if effect.inferred_dirty and not effect.declared_dirty:
                self._raise_error(
                    f"word '{word_name}' inferred dirty but missing dirty annotation",
                    line,
                    column,
                    span=span,
                )
            if not effect.inferred_dirty and effect.declared_dirty:
                self._raise_error(
                    f"word '{word_name}' annotated dirty but inferred pure",
                    line,
                    column,
                    span=span,
                )

    def _iter_top_level_words(self, program: ProgramNode) -> list[WordDefNode]:
        words: list[WordDefNode] = []
        for declaration in program.declarations:
            if not isinstance(declaration, ModuleDeclaration):
                continue
            for item in declaration.items:
                if isinstance(item, WordDefNode):
                    words.append(item)
        return words


_CHECKER_MESSAGE_CODE_MAP = {
    "word body does not match declared outputs": "CHECKER_WORD_OUTPUT_MISMATCH",
    "Ok! value type does not match frame Result value type": "CHECKER_RESULT_OK_VALUE_TYPE_MISMATCH",
    "Err! error type does not match frame Result error type": "CHECKER_RESULT_ERR_ERROR_TYPE_MISMATCH",
    "? expects Result<T,E>": "CHECKER_PROPAGATE_EXPECTS_RESULT",
    "? requires frame output to be exactly one Result<T,E>": "CHECKER_PROPAGATE_REQUIRES_RESULT_OUTPUT",
    "? error type must exactly match frame Result error type": "CHECKER_PROPAGATE_ERROR_TYPE_MISMATCH",
    "unresolved host signature during checking": "CHECKER_UNRESOLVED_HOST_SIGNATURE",
    "unresolved identifier during checking": "CHECKER_UNRESOLVED_IDENTIFIER",
    "result.unwrap-or expects Result<T,E> T": "CHECKER_RESULT_UNWRAP_OR_EXPECTS_RESULT_AND_FALLBACK",
    "result.unwrap-or fallback type must match Result value type": "CHECKER_RESULT_UNWRAP_OR_FALLBACK_TYPE_MISMATCH",
    "list.len expects List<T>": "CHECKER_LIST_LEN_EXPECTS_LIST",
    "list.is-empty expects List<T>": "CHECKER_LIST_IS_EMPTY_EXPECTS_LIST",
    "list.first expects List<T>": "CHECKER_LIST_FIRST_EXPECTS_LIST",
    "list.last expects List<T>": "CHECKER_LIST_LAST_EXPECTS_LIST",
    "list.append expects List<T> T": "CHECKER_LIST_APPEND_EXPECTS_LIST_AND_VALUE",
    "list.append value type does not match list element type": "CHECKER_LIST_APPEND_VALUE_TYPE_MISMATCH",
    "list.reverse expects List<T>": "CHECKER_LIST_REVERSE_EXPECTS_LIST",
    "list.concat expects List<T> List<T>": "CHECKER_LIST_CONCAT_EXPECTS_LISTS",
    "list.concat expects matching list element types": "CHECKER_LIST_CONCAT_ELEMENT_TYPE_MISMATCH",
    "list.get expects List<T> Int": "CHECKER_LIST_GET_EXPECTS_LIST_AND_INT",
    "list.get index must be Int": "CHECKER_LIST_GET_INDEX_NOT_INT",
    "list.map expects List<T> (Quote|DirtyQuote)<{ | x:T -- y:U }>": "CHECKER_LIST_MAP_EXPECTS_LIST_AND_QUOTE",
    "list.map quotation must have one input and one output": "CHECKER_LIST_MAP_QUOTE_ARITY",
    "list.map quotation input type does not match list element type": "CHECKER_LIST_MAP_INPUT_TYPE_MISMATCH",
    "list.filter expects List<T> (Quote|DirtyQuote)<{ | x:T -- keep:Bool }>": "CHECKER_LIST_FILTER_EXPECTS_LIST_AND_QUOTE",
    "list.filter quotation must have one input and one output": "CHECKER_LIST_FILTER_QUOTE_ARITY",
    "list.filter quotation input type does not match list element type": "CHECKER_LIST_FILTER_INPUT_TYPE_MISMATCH",
    "list.filter quotation output type must be Bool": "CHECKER_LIST_FILTER_OUTPUT_NOT_BOOL",
    "list.set expects List<T> Int T": "CHECKER_LIST_SET_EXPECTS_LIST_INT_VALUE",
    "list.set index must be Int": "CHECKER_LIST_SET_INDEX_NOT_INT",
    "list.set value type does not match list element type": "CHECKER_LIST_SET_VALUE_TYPE_MISMATCH",
    "list.fold expects List<T> Acc (Quote|DirtyQuote)<{ | acc:Acc x:T -- out:Acc }>": "CHECKER_LIST_FOLD_EXPECTS_LIST_ACC_QUOTE",
    "list.fold quotation must have two inputs and one output": "CHECKER_LIST_FOLD_QUOTE_ARITY",
    "list.fold quotation accumulator type does not match init type": "CHECKER_LIST_FOLD_ACCUMULATOR_TYPE_MISMATCH",
    "list.fold quotation item type does not match list element type": "CHECKER_LIST_FOLD_ITEM_TYPE_MISMATCH",
    "list.fold quotation output type does not match accumulator type": "CHECKER_LIST_FOLD_OUTPUT_TYPE_MISMATCH",
    "list.reduce expects List<T> (Quote|DirtyQuote)<{ | a:T b:T -- c:T }>": "CHECKER_LIST_REDUCE_EXPECTS_LIST_AND_QUOTE",
    "list.reduce cannot be applied to a provably empty list": "CHECKER_LIST_REDUCE_EMPTY_LIST",
    "list.reduce quotation must have two inputs and one output": "CHECKER_LIST_REDUCE_QUOTE_ARITY",
    "list.reduce first quotation input type does not match list element type": "CHECKER_LIST_REDUCE_FIRST_INPUT_TYPE_MISMATCH",
    "list.reduce second quotation input type does not match list element type": "CHECKER_LIST_REDUCE_SECOND_INPUT_TYPE_MISMATCH",
    "list.reduce quotation output type does not match list element type": "CHECKER_LIST_REDUCE_OUTPUT_TYPE_MISMATCH",
    "map.len expects Map<K,V>": "CHECKER_MAP_LEN_EXPECTS_MAP",
    "map.is-empty expects Map<K,V>": "CHECKER_MAP_IS_EMPTY_EXPECTS_MAP",
    "map.keys expects Map<K,V>": "CHECKER_MAP_KEYS_EXPECTS_MAP",
    "map.values expects Map<K,V>": "CHECKER_MAP_VALUES_EXPECTS_MAP",
    "map.contains expects Map<K,V> K": "CHECKER_MAP_CONTAINS_EXPECTS_MAP_AND_KEY",
    "map.contains key type does not match map key type": "CHECKER_MAP_CONTAINS_KEY_TYPE_MISMATCH",
    "map.get expects Map<K,V> K": "CHECKER_MAP_GET_EXPECTS_MAP_AND_KEY",
    "map.get key type does not match map key type": "CHECKER_MAP_GET_KEY_TYPE_MISMATCH",
    "map.set expects Map<K,V> K V": "CHECKER_MAP_SET_EXPECTS_MAP_KEY_VALUE",
    "map.set key type does not match map key type": "CHECKER_MAP_SET_KEY_TYPE_MISMATCH",
    "map.set value type does not match map value type": "CHECKER_MAP_SET_VALUE_TYPE_MISMATCH",
    "map.remove expects Map<K,V> K": "CHECKER_MAP_REMOVE_EXPECTS_MAP_AND_KEY",
    "map.remove key type does not match map key type": "CHECKER_MAP_REMOVE_KEY_TYPE_MISMATCH",
    "call expects Quote<{ ... }> or DirtyQuote<{ ... }>": "CHECKER_CALL_EXPECTS_QUOTE",
    "call input types do not match quotation inputs": "CHECKER_CALL_INPUT_TYPE_MISMATCH",
    "invalid arithmetic operand types": "CHECKER_INVALID_ARITHMETIC_OPERAND_TYPES",
    "invalid comparison operand types": "CHECKER_INVALID_COMPARISON_OPERAND_TYPES",
    "equality is not supported for host opaque types": "CHECKER_OPAQUE_EQUALITY_UNSUPPORTED",
    "invalid equality operand types": "CHECKER_INVALID_EQUALITY_OPERAND_TYPES",
    "invalid boolean operand types": "CHECKER_INVALID_BOOLEAN_OPERAND_TYPES",
    "if condition must be Bool": "CHECKER_IF_CONDITION_NOT_BOOL",
    "if branches have incompatible stack effects": "CHECKER_IF_BRANCH_STACK_MISMATCH",
    "case must have at least one branch": "CHECKER_CASE_EMPTY",
    "case branches have incompatible stack effects": "CHECKER_CASE_BRANCH_STACK_MISMATCH",
    "case is not exhaustive": "CHECKER_CASE_NOT_EXHAUSTIVE",
    "case guard cannot contain ?": "CHECKER_CASE_GUARD_CONTAINS_PROPAGATE",
    "case guard must not consume preexisting stack values": "CHECKER_CASE_GUARD_CONSUMES_STACK",
    "case guard must produce exactly one Bool": "CHECKER_CASE_GUARD_WRONG_ARITY",
    "case guard must produce Bool": "CHECKER_CASE_GUARD_NOT_BOOL",
    "case pattern does not match scrutinee type": "CHECKER_CASE_PATTERN_TYPE_MISMATCH",
    "unsupported case pattern": "CHECKER_UNSUPPORTED_CASE_PATTERN",
    "Ok/Err pattern requires Result scrutinee": "CHECKER_RESULT_PATTERN_EXPECTS_RESULT",
    "unsupported Result type argument": "CHECKER_UNSUPPORTED_RESULT_TYPE_ARGUMENT",
    "quotation capture types do not match": "CHECKER_QUOTE_CAPTURE_TYPE_MISMATCH",
    "quotation body does not match declared outputs": "CHECKER_QUOTE_OUTPUT_MISMATCH",
    "list literal elements must have the same type": "CHECKER_LIST_LITERAL_ELEMENT_TYPE_MISMATCH",
    "list literal element must produce exactly one value": "CHECKER_LIST_LITERAL_ELEMENT_ARITY",
    "type mismatch in word call": "CHECKER_WORD_CALL_TYPE_MISMATCH",
    "insufficient stack": "CHECKER_INSUFFICIENT_STACK",
    "pure frame cannot construct DirtyQuote": "CHECKER_PURE_FRAME_CONSTRUCTS_DIRTY_QUOTE",
    "pure frame cannot call DirtyQuote": "CHECKER_PURE_FRAME_CALLS_DIRTY_QUOTE",
    "case guard cannot call dirty code": "CHECKER_CASE_GUARD_CALLS_DIRTY_CODE",
    "Map<K,V> key type must be Int, String, or Bool in v1": "CHECKER_INVALID_MAP_KEY_TYPE",
    "host capability cannot be used as a type": "CHECKER_HOST_CAPABILITY_TYPE_USE",
}


def _checker_code_for_message(message: str) -> str:
    code = _CHECKER_MESSAGE_CODE_MAP.get(message)
    if code is not None:
        return code
    if message.startswith("type is not supported in v1: "):
        return "CHECKER_UNSUPPORTED_TYPE_V1"
    if message.startswith("undeclared host opaque type in checker: "):
        return "CHECKER_UNDECLARED_HOST_OPAQUE_TYPE"
    if message.endswith(" expects Result<T,E>"):
        return "CHECKER_RESULT_PREDICATE_EXPECTS_RESULT"
    if message.startswith("pure frame cannot pass DirtyQuote to "):
        return "CHECKER_PURE_FRAME_PASSES_DIRTY_QUOTE"
    if message.startswith("pure word '") and "' cannot call dirty word '" in message:
        return "CHECKER_PURE_WORD_CALLS_DIRTY_WORD"
    if message.startswith("word '") and message.endswith("' inferred dirty but missing dirty annotation"):
        return "CHECKER_DIRTY_ANNOTATION_MISSING"
    if message.startswith("word '") and message.endswith("' annotated dirty but inferred pure"):
        return "CHECKER_DIRTY_ANNOTATION_REDUNDANT"
    return "CHECKER_INVALID_TYPE_V1"


def check(
    program: ProgramNode,
    symbols: SymbolTable,
    *,
    declared_opaque_type_names: frozenset[str] = frozenset(),
) -> ProgramNode:
    return Checker(
        symbols,
        declared_opaque_type_names=declared_opaque_type_names,
    ).check(program)


def check_program(
    program: ProgramNode,
    symbols: SymbolTable,
    *,
    declared_opaque_type_names: frozenset[str] = frozenset(),
) -> ProgramNode:
    return check(
        program,
        symbols,
        declared_opaque_type_names=declared_opaque_type_names,
    )


def _literal_type(node: LiteralNode) -> TypeNode:
    if node.kind is LiteralKind.INT:
        return _builtin_type("Int")
    if node.kind is LiteralKind.FLOAT:
        return _builtin_type("Float")
    if node.kind is LiteralKind.STRING:
        return _builtin_type("String")
    if node.kind is LiteralKind.BOOL:
        return _builtin_type("Bool")
    raise NotImplementedError(f"literal type checking not implemented for {node.kind}")


def _builtin_type(name: str) -> TypeNode:
    from .tokens import SourceSpan

    return TypeNode(span=SourceSpan(line=0, column=0, offset=0), name=name)


def _validate_language_type_v1(
    type_node: TypeNode,
    *,
    declared_opaque_type_names: frozenset[str] = frozenset(),
    resolve_import_category: Callable[[str], SymbolCategory | None] | None = None,
) -> None:
    imported_type_category = resolve_import_category(type_node.name) if resolve_import_category is not None else None
    if imported_type_category is SymbolCategory.HOST_OPAQUE_TYPE:
        if type_node.args:
            raise HostABIError(f"type is not supported in v1: {type_node.name}")
        return
    if imported_type_category is SymbolCategory.HOST_CAPABILITY:
        raise HostABIError("host capability cannot be used as a type")

    if type_node.name.startswith("@host."):
        legacy_name = type_node.name[1:]
        if legacy_name in declared_opaque_type_names:
            if type_node.args:
                raise HostABIError(f"type is not supported in v1: {type_node.name}")
            return
        raise HostABIError(f"undeclared host opaque type in checker: {type_node.name}")

    if type_node.name in declared_opaque_type_names:
        if type_node.args:
            raise HostABIError(f"type is not supported in v1: {type_node.name}")
        return

    if type_node.name.startswith("host."):
        raise HostABIError(f"undeclared host opaque type in checker: {type_node.name}")

    if type_node.name in _LANGUAGE_SCALAR_TYPES_V1:
        if type_node.args:
            raise HostABIError(f"type is not supported in v1: {type_node.name}")
        return

    if type_node.name == "List":
        if len(type_node.args) != 1 or not isinstance(type_node.args[0], TypeNode):
            raise HostABIError("type is not supported in v1: List")
        _validate_language_type_v1(
            type_node.args[0],
            declared_opaque_type_names=declared_opaque_type_names,
            resolve_import_category=resolve_import_category,
        )
        return

    if type_node.name == "Map":
        if len(type_node.args) != 2:
            raise HostABIError("type is not supported in v1: Map")
        key_type = type_node.args[0]
        value_type = type_node.args[1]
        if not isinstance(key_type, TypeNode) or not isinstance(value_type, TypeNode):
            raise HostABIError("type is not supported in v1: Map")
        if key_type.name not in {"Int", "String", "Bool"}:
            raise HostABIError("Map<K,V> key type must be Int, String, or Bool in v1")
        _validate_language_type_v1(
            key_type,
            declared_opaque_type_names=declared_opaque_type_names,
            resolve_import_category=resolve_import_category,
        )
        _validate_language_type_v1(
            value_type,
            declared_opaque_type_names=declared_opaque_type_names,
            resolve_import_category=resolve_import_category,
        )
        return

    if type_node.name == "Result":
        if len(type_node.args) != 2:
            raise HostABIError("type is not supported in v1: Result")
        value_type = type_node.args[0]
        error_type = type_node.args[1]
        if not isinstance(value_type, TypeNode) or not isinstance(error_type, TypeNode):
            raise HostABIError("type is not supported in v1: Result")
        _validate_language_type_v1(
            value_type,
            declared_opaque_type_names=declared_opaque_type_names,
            resolve_import_category=resolve_import_category,
        )
        _validate_language_type_v1(
            error_type,
            declared_opaque_type_names=declared_opaque_type_names,
            resolve_import_category=resolve_import_category,
        )
        return

    if type_node.name in {"Quote", "DirtyQuote"}:
        if len(type_node.args) != 1 or not isinstance(type_node.args[0], QuoteTypeNode):
            raise HostABIError(f"type is not supported in v1: {type_node.name}")
        quote_signature = type_node.args[0]
        for parameter in quote_signature.captures:
            _validate_language_type_v1(
                parameter.type_node,
                declared_opaque_type_names=declared_opaque_type_names,
                resolve_import_category=resolve_import_category,
            )
        for parameter in quote_signature.inputs:
            _validate_language_type_v1(
                parameter.type_node,
                declared_opaque_type_names=declared_opaque_type_names,
                resolve_import_category=resolve_import_category,
            )
        for parameter in quote_signature.outputs:
            _validate_language_type_v1(
                parameter.type_node,
                declared_opaque_type_names=declared_opaque_type_names,
                resolve_import_category=resolve_import_category,
            )
        return

    raise HostABIError(f"type is not supported in v1: {type_node.name}")


def _result_type(span, value_type: TypeNode, error_type: TypeNode) -> TypeNode:
    return TypeNode(span=span, name="Result", args=(value_type, error_type))


def _is_named_type(type_node: TypeNode, name: str) -> bool:
    return type_node.name == name and len(type_node.args) == 0


def _extract_list_item_type(type_node: TypeNode) -> TypeNode | None:
    if type_node.name != "List" or len(type_node.args) != 1:
        return None
    item_type = type_node.args[0]
    if not isinstance(item_type, TypeNode):
        return None
    return item_type


def _extract_map_types(type_node: TypeNode) -> tuple[TypeNode, TypeNode] | None:
    if type_node.name != "Map" or len(type_node.args) != 2:
        return None
    key_type = type_node.args[0]
    value_type = type_node.args[1]
    if not isinstance(key_type, TypeNode) or not isinstance(value_type, TypeNode):
        return None
    return key_type, value_type


def _extract_quote_signature(type_node: TypeNode) -> QuoteTypeNode | None:
    if type_node.name not in {"Quote", "DirtyQuote"} or len(type_node.args) != 1:
        return None
    signature = type_node.args[0]
    if not isinstance(signature, QuoteTypeNode):
        return None
    return signature


def _extract_result_types(type_node: TypeNode) -> tuple[TypeNode, TypeNode] | None:
    if type_node.name != "Result" or len(type_node.args) != 2:
        return None
    value_type = type_node.args[0]
    error_type = type_node.args[1]
    if not isinstance(value_type, TypeNode) or not isinstance(error_type, TypeNode):
        return None
    return value_type, error_type


def _single_result_output_type(outputs) -> TypeNode | None:
    if len(outputs) != 1:
        return None
    result_type = outputs[0].type_node
    if _extract_result_types(result_type) is None:
        return None
    return result_type


def _pattern_literal_type(value: object) -> TypeNode:
    if isinstance(value, bool):
        return _builtin_type("Bool")
    if isinstance(value, int):
        return _builtin_type("Int")
    if isinstance(value, float):
        return _builtin_type("Float")
    if isinstance(value, str):
        return _builtin_type("String")
    raise NotImplementedError(f"pattern type checking not implemented for {type(value).__name__}")


def _same_stack(left, right: list[TypeNode]) -> bool:
    if len(left) != len(right):
        return False
    return all(_same_type(_stack_item_type(left_item), _stack_item_type(right_item)) for left_item, right_item in zip(left, right))


def _stack_item_type(item) -> TypeNode:
    if isinstance(item, StackValue):
        return item.type_node
    return item


def _same_type(left: TypeNode, right: TypeNode) -> bool:
    if left.name != right.name:
        return False
    if len(left.args) != len(right.args):
        return False
    for left_arg, right_arg in zip(left.args, right.args):
        if isinstance(left_arg, TypeNode) and isinstance(right_arg, TypeNode):
            if not _same_type(left_arg, right_arg):
                return False
            continue
        if isinstance(left_arg, QuoteTypeNode) and isinstance(right_arg, QuoteTypeNode):
            if not _same_quote_type(left_arg, right_arg):
                return False
            continue
        return False
    return True


def _same_quote_type(left: QuoteTypeNode, right: QuoteTypeNode) -> bool:
    return (
        left.effect_kind is right.effect_kind
        and
        _same_parameter_types(left.captures, right.captures)
        and _same_parameter_types(left.inputs, right.inputs)
        and _same_parameter_types(left.outputs, right.outputs)
    )


def _same_parameter_types(left, right) -> bool:
    if len(left) != len(right):
        return False
    return all(_same_type(left_parameter.type_node, right_parameter.type_node) for left_parameter, right_parameter in zip(left, right))


def _is_case_exhaustive(node: CaseNode, scrutinee_type: TypeNode) -> bool:
    if any(
        branch.pattern.kind is PatternKind.WILDCARD and branch.guard is None
        for branch in node.branches
    ):
        return True

    patterns = [branch.pattern for branch in node.branches if branch.guard is None]

    if _is_named_type(scrutinee_type, "Bool"):
        seen = {pattern.value for pattern in patterns if pattern.kind is PatternKind.LITERAL and isinstance(pattern.value, bool)}
        return seen == {True, False}

    result_error_variants = _result_error_variants(scrutinee_type)
    if result_error_variants is not None:
        has_ok = any(pattern.kind is PatternKind.OK for pattern in patterns)
        if not has_ok:
            return False
        err_covered = False
        for pattern in patterns:
            if pattern.kind is not PatternKind.ERR:
                continue
            if pattern.binding is not None:
                err_covered = True
                break
            if pattern.value in result_error_variants:
                err_covered = True
                break
        return err_covered

    if _is_named_type(scrutinee_type, "MapError"):
        return any(
            (
                pattern.kind is PatternKind.NAME
                and pattern.value == "MissingKey"
            )
            for pattern in patterns
        )

    if _is_named_type(scrutinee_type, "ListError"):
        return any(
            (
                pattern.kind is PatternKind.NAME
                and pattern.value == "OutOfBounds"
            )
            for pattern in patterns
        )

    return True


def _is_valid_closed_variant_pattern(scrutinee_type: TypeNode, variant_name: str) -> bool:
    if _is_named_type(scrutinee_type, "MapError"):
        return variant_name == "MissingKey"
    if _is_named_type(scrutinee_type, "ListError"):
        return variant_name == "OutOfBounds"
    return False


def _is_valid_result_error_variant(scrutinee_type: TypeNode, variant_name: str) -> bool:
    variants = _result_error_variants(scrutinee_type)
    if variants is None:
        return False
    return variant_name in variants


def _result_error_variants(scrutinee_type: TypeNode) -> set[str] | None:
    if scrutinee_type.name != "Result" or len(scrutinee_type.args) != 2:
        return None
    error_type = scrutinee_type.args[1]
    if not isinstance(error_type, TypeNode):
        return None
    if _is_named_type(error_type, "MapError"):
        return {"MissingKey"}
    if _is_named_type(error_type, "ListError"):
        return {"OutOfBounds"}
    return None


def _error_variant_expression_type(variant_name: str, span: SourceSpan) -> TypeNode | None:
    if variant_name == "MissingKey":
        return TypeNode(span=span, name="MapError")
    if variant_name == "OutOfBounds":
        return TypeNode(span=span, name="ListError")
    return None


def _qualified_name(owner: str | None, name: str) -> str:
    if owner is None:
        return name
    return f"{owner}.{name}"


def _word_identity(module_name: str, qualified_name: str) -> str:
    return f"@{module_name}.{qualified_name}"


def _symbol_word_identity(symbol: WordSymbol) -> str | None:
    if symbol.module is None:
        return None
    return _word_identity(symbol.module, symbol.qualified_name)


def _compute_sccs(
    graph: dict[str, set[str]],
    node_order: list[str],
) -> tuple[list[list[str]], dict[str, int]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    components: list[list[str]] = []
    component_by_word: dict[str, int] = {}

    def strong_connect(node: str) -> None:
        nonlocal index
        indices[node] = index
        low_links[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in sorted(graph[node]):
            if neighbor not in indices:
                strong_connect(neighbor)
                low_links[node] = min(low_links[node], low_links[neighbor])
            elif neighbor in on_stack:
                low_links[node] = min(low_links[node], indices[neighbor])

        if low_links[node] == indices[node]:
            component: list[str] = []
            while stack:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            component_id = len(components)
            components.append(component)
            for member in component:
                component_by_word[member] = component_id

    for node in node_order:
        if node not in indices:
            strong_connect(node)

    return components, component_by_word
