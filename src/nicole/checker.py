from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import (
    BlockNode,
    CaseNode,
    IdentifierNode,
    IfNode,
    ListLiteralNode,
    LiteralKind,
    LiteralNode,
    OperatorNode,
    PatternKind,
    ProgramNode,
    QuoteNode,
    QuoteTypeNode,
    TypeNode,
    TypedEmptyListNode,
    TypedEmptyMapNode,
    WordDefNode,
)
from .symbols import SymbolSource, SymbolTable

__all__ = ["Checker", "CheckerError", "check", "check_program"]


@dataclass(slots=True)
class CheckerError(Exception):
    message: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.message} at {self.line}:{self.column}"


@dataclass(frozen=True, slots=True)
class StackValue:
    type_node: TypeNode
    known_empty_list: bool = False


class Checker:
    def __init__(self, symbols: SymbolTable) -> None:
        self._symbols = symbols

    def check(self, program: ProgramNode) -> ProgramNode:
        for word in program.words:
            self._check_word(word)
        return program

    def _check_word(self, word: WordDefNode) -> None:
        local_types = {parameter.name: parameter.type_node for parameter in word.signature.inputs}
        end_stack = self._check_block(word.body, [], local_types)
        expected_outputs = [parameter.type_node for parameter in word.signature.outputs]
        if not _same_stack(end_stack, expected_outputs):
            self._raise_error("word body does not match declared outputs", word.span.line, word.span.column)

        for nested_word in word.nested_words:
            self._check_word(nested_word)

    def _check_block(
        self,
        block: BlockNode,
        stack: list[TypeNode],
        local_types: dict[str, TypeNode],
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
                current_stack = self._check_if(item, current_stack, local_types)
            elif isinstance(item, CaseNode):
                current_stack = self._check_case(item, current_stack, local_types)
            elif isinstance(item, ListLiteralNode):
                current_stack.append(StackValue(self._check_list_literal(item, local_types)))
            elif isinstance(item, QuoteNode):
                current_stack = self._check_quote(item, current_stack)
            else:
                raise NotImplementedError(f"checking not implemented for {type(item).__name__}")
        return current_stack

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
                self._raise_error("unresolved host signature during checking", node.span.line, node.span.column)
            self._apply_signature(node.span.line, node.span.column, stack, signature.inputs, signature.outputs)
            return

        symbol = node.resolution.resolved_symbol
        if symbol is None:
            self._raise_error("unresolved identifier during checking", node.span.line, node.span.column)

        if symbol.source is SymbolSource.BUILTIN:
            self._check_builtin(node, stack)
            return

        self._apply_signature(node.span.line, node.span.column, stack, symbol.signature.inputs, symbol.signature.outputs)

    def _check_builtin(self, node: IdentifierNode, stack: list[TypeNode]) -> None:
        if node.name == "list.len":
            collection_type = self._pop_type(stack, node.span.line, node.span.column)
            if _extract_list_item_type(collection_type) is None:
                self._raise_error("list.len expects List<T>", node.span.line, node.span.column)
            stack.append(StackValue(_builtin_type("Int")))
            return

        if node.name == "list.concat":
            right_type = self._pop_type(stack, node.span.line, node.span.column)
            left_type = self._pop_type(stack, node.span.line, node.span.column)
            right_item_type = _extract_list_item_type(right_type)
            left_item_type = _extract_list_item_type(left_type)
            if right_item_type is None or left_item_type is None:
                self._raise_error("list.concat expects List<T> List<T>", node.span.line, node.span.column)
            if not _same_type(left_item_type, right_item_type):
                self._raise_error("list.concat expects matching list element types", node.span.line, node.span.column)
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(left_item_type,))))
            return

        if node.name == "list.get":
            index_type = self._pop_type(stack, node.span.line, node.span.column)
            list_type = self._pop_type(stack, node.span.line, node.span.column)
            item_type = _extract_list_item_type(list_type)
            if item_type is None:
                self._raise_error("list.get expects List<T> Int", node.span.line, node.span.column)
            if not _is_named_type(index_type, "Int"):
                self._raise_error("list.get index must be Int", node.span.line, node.span.column)
            stack.append(StackValue(_result_type(node.span, item_type, _builtin_type("ListError"))))
            return

        if node.name == "list.map":
            quote_type = self._pop_type(stack, node.span.line, node.span.column)
            list_type = self._pop_type(stack, node.span.line, node.span.column)
            item_type = _extract_list_item_type(list_type)
            quote_signature = _extract_quote_signature(quote_type)
            if item_type is None or quote_signature is None:
                self._raise_error("list.map expects List<T> Quote<{ | x:T -- y:U }>", node.span.line, node.span.column)
            if len(quote_signature.inputs) != 1 or len(quote_signature.outputs) != 1:
                self._raise_error("list.map quotation must have one input and one output", node.span.line, node.span.column)
            quote_input_type = quote_signature.inputs[0].type_node
            quote_output_type = quote_signature.outputs[0].type_node
            if not _same_type(quote_input_type, item_type):
                self._raise_error("list.map quotation input type does not match list element type", node.span.line, node.span.column)
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(quote_output_type,))))
            return

        if node.name == "list.set":
            value_type = self._pop_type(stack, node.span.line, node.span.column)
            index_type = self._pop_type(stack, node.span.line, node.span.column)
            list_type = self._pop_type(stack, node.span.line, node.span.column)
            item_type = _extract_list_item_type(list_type)
            if item_type is None:
                self._raise_error("list.set expects List<T> Int T", node.span.line, node.span.column)
            if not _is_named_type(index_type, "Int"):
                self._raise_error("list.set index must be Int", node.span.line, node.span.column)
            if not _same_type(value_type, item_type):
                self._raise_error("list.set value type does not match list element type", node.span.line, node.span.column)
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
            quote_type = self._pop_type(stack, node.span.line, node.span.column)
            accumulator_type = self._pop_type(stack, node.span.line, node.span.column)
            list_type = self._pop_type(stack, node.span.line, node.span.column)
            item_type = _extract_list_item_type(list_type)
            quote_signature = _extract_quote_signature(quote_type)
            if item_type is None or quote_signature is None:
                self._raise_error("list.fold expects List<T> Acc Quote<{ | acc:Acc x:T -- out:Acc }>", node.span.line, node.span.column)
            if len(quote_signature.inputs) != 2 or len(quote_signature.outputs) != 1:
                self._raise_error("list.fold quotation must have two inputs and one output", node.span.line, node.span.column)
            if not _same_type(quote_signature.inputs[0].type_node, accumulator_type):
                self._raise_error("list.fold quotation accumulator type does not match init type", node.span.line, node.span.column)
            if not _same_type(quote_signature.inputs[1].type_node, item_type):
                self._raise_error("list.fold quotation item type does not match list element type", node.span.line, node.span.column)
            if not _same_type(quote_signature.outputs[0].type_node, accumulator_type):
                self._raise_error("list.fold quotation output type does not match accumulator type", node.span.line, node.span.column)
            stack.append(StackValue(accumulator_type))
            return

        if node.name == "list.reduce":
            quote_type = self._pop_type(stack, node.span.line, node.span.column)
            list_value = self._pop_value(stack, node.span.line, node.span.column)
            list_type = list_value.type_node
            item_type = _extract_list_item_type(list_type)
            quote_signature = _extract_quote_signature(quote_type)
            if item_type is None or quote_signature is None:
                self._raise_error("list.reduce expects List<T> Quote<{ | a:T b:T -- c:T }>", node.span.line, node.span.column)
            if list_value.known_empty_list:
                self._raise_error("list.reduce cannot be applied to a provably empty list", node.span.line, node.span.column)
            if len(quote_signature.inputs) != 2 or len(quote_signature.outputs) != 1:
                self._raise_error("list.reduce quotation must have two inputs and one output", node.span.line, node.span.column)
            if not _same_type(quote_signature.inputs[0].type_node, item_type):
                self._raise_error("list.reduce first quotation input type does not match list element type", node.span.line, node.span.column)
            if not _same_type(quote_signature.inputs[1].type_node, item_type):
                self._raise_error("list.reduce second quotation input type does not match list element type", node.span.line, node.span.column)
            if not _same_type(quote_signature.outputs[0].type_node, item_type):
                self._raise_error("list.reduce quotation output type does not match list element type", node.span.line, node.span.column)
            stack.append(StackValue(item_type))
            return

        if node.name == "map.len":
            collection_type = self._pop_type(stack, node.span.line, node.span.column)
            if _extract_map_types(collection_type) is None:
                self._raise_error("map.len expects Map<K,V>", node.span.line, node.span.column)
            stack.append(StackValue(_builtin_type("Int")))
            return

        if node.name == "map.contains":
            key_type = self._pop_type(stack, node.span.line, node.span.column)
            map_type = self._pop_type(stack, node.span.line, node.span.column)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.contains expects Map<K,V> K", node.span.line, node.span.column)
            expected_key_type, _ = map_parts
            if not _same_type(key_type, expected_key_type):
                self._raise_error("map.contains key type does not match map key type", node.span.line, node.span.column)
            stack.append(StackValue(_builtin_type("Bool")))
            return

        if node.name == "map.get":
            key_type = self._pop_type(stack, node.span.line, node.span.column)
            map_type = self._pop_type(stack, node.span.line, node.span.column)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.get expects Map<K,V> K", node.span.line, node.span.column)
            expected_key_type, value_type = map_parts
            if not _same_type(key_type, expected_key_type):
                self._raise_error("map.get key type does not match map key type", node.span.line, node.span.column)
            stack.append(StackValue(_result_type(node.span, value_type, _builtin_type("MapError"))))
            return

        if node.name == "map.set":
            value_type = self._pop_type(stack, node.span.line, node.span.column)
            key_type = self._pop_type(stack, node.span.line, node.span.column)
            map_type = self._pop_type(stack, node.span.line, node.span.column)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.set expects Map<K,V> K V", node.span.line, node.span.column)
            expected_key_type, expected_value_type = map_parts
            if not _same_type(key_type, expected_key_type):
                self._raise_error("map.set key type does not match map key type", node.span.line, node.span.column)
            if not _same_type(value_type, expected_value_type):
                self._raise_error("map.set value type does not match map value type", node.span.line, node.span.column)
            stack.append(StackValue(TypeNode(span=node.span, name="Map", args=(expected_key_type, expected_value_type))))
            return

        if node.name == "map.remove":
            key_type = self._pop_type(stack, node.span.line, node.span.column)
            map_type = self._pop_type(stack, node.span.line, node.span.column)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.remove expects Map<K,V> K", node.span.line, node.span.column)
            expected_key_type, value_type = map_parts
            if not _same_type(key_type, expected_key_type):
                self._raise_error("map.remove key type does not match map key type", node.span.line, node.span.column)
            stack.append(StackValue(TypeNode(span=node.span, name="Map", args=(expected_key_type, value_type))))
            return

        if node.name == "map.keys":
            map_type = self._pop_type(stack, node.span.line, node.span.column)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.keys expects Map<K,V>", node.span.line, node.span.column)
            key_type, _ = map_parts
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(key_type,))))
            return

        if node.name == "map.values":
            map_type = self._pop_type(stack, node.span.line, node.span.column)
            map_parts = _extract_map_types(map_type)
            if map_parts is None:
                self._raise_error("map.values expects Map<K,V>", node.span.line, node.span.column)
            _, value_type = map_parts
            stack.append(StackValue(TypeNode(span=node.span, name="List", args=(value_type,))))
            return

        raise NotImplementedError("builtin checking is not implemented")

    def _check_operator(self, node: OperatorNode, stack: list[TypeNode]) -> None:
        if node.operator == "call":
            quote_type = self._pop_type(stack, node.span.line, node.span.column)
            quote_signature = _extract_quote_signature(quote_type)
            if quote_signature is None:
                self._raise_error("call expects Quote<{ ... }>", node.span.line, node.span.column)
            for parameter in reversed(quote_signature.inputs):
                actual = self._pop_type(stack, node.span.line, node.span.column)
                if not _same_type(actual, parameter.type_node):
                    self._raise_error("call input types do not match quotation inputs", node.span.line, node.span.column)
            for parameter in quote_signature.outputs:
                stack.append(StackValue(parameter.type_node))
            return

        if node.operator == "drop":
            self._pop_value(stack, node.span.line, node.span.column)
            return

        if node.operator == "dup":
            value = self._pop_value(stack, node.span.line, node.span.column)
            stack.append(value)
            stack.append(value)
            return

        if node.operator == "swap":
            right = self._pop_value(stack, node.span.line, node.span.column)
            left = self._pop_value(stack, node.span.line, node.span.column)
            stack.append(right)
            stack.append(left)
            return

        if node.operator == "over":
            right = self._pop_value(stack, node.span.line, node.span.column)
            left = self._pop_value(stack, node.span.line, node.span.column)
            stack.append(left)
            stack.append(right)
            stack.append(left)
            return

        if node.operator == "rot":
            third = self._pop_value(stack, node.span.line, node.span.column)
            second = self._pop_value(stack, node.span.line, node.span.column)
            first = self._pop_value(stack, node.span.line, node.span.column)
            stack.append(second)
            stack.append(third)
            stack.append(first)
            return

        if node.operator in {"+", "-", "*", "div", "mod"}:
            right = self._pop_type(stack, node.span.line, node.span.column)
            left = self._pop_type(stack, node.span.line, node.span.column)
            if _is_named_type(left, "Int") and _is_named_type(right, "Int"):
                stack.append(StackValue(_builtin_type("Int")))
                return
            self._raise_error("invalid arithmetic operand types", node.span.line, node.span.column)

        if node.operator in {"+.", "-.", "*.", "/."}:
            right = self._pop_type(stack, node.span.line, node.span.column)
            left = self._pop_type(stack, node.span.line, node.span.column)
            if _is_named_type(left, "Float") and _is_named_type(right, "Float"):
                stack.append(StackValue(_builtin_type("Float")))
                return
            self._raise_error("invalid arithmetic operand types", node.span.line, node.span.column)

        if node.operator in {"<", "<=", ">", ">="}:
            right = self._pop_type(stack, node.span.line, node.span.column)
            left = self._pop_type(stack, node.span.line, node.span.column)
            if (
                _is_named_type(left, "Int") and _is_named_type(right, "Int")
            ) or (
                _is_named_type(left, "Float") and _is_named_type(right, "Float")
            ):
                stack.append(StackValue(_builtin_type("Bool")))
                return
            self._raise_error("invalid comparison operand types", node.span.line, node.span.column)

        if node.operator in {"=", "!="}:
            right = self._pop_type(stack, node.span.line, node.span.column)
            left = self._pop_type(stack, node.span.line, node.span.column)
            if _same_type(left, right):
                stack.append(StackValue(_builtin_type("Bool")))
                return
            self._raise_error("invalid equality operand types", node.span.line, node.span.column)

        if node.operator in {"and", "or"}:
            right = self._pop_type(stack, node.span.line, node.span.column)
            left = self._pop_type(stack, node.span.line, node.span.column)
            if _is_named_type(left, "Bool") and _is_named_type(right, "Bool"):
                stack.append(StackValue(_builtin_type("Bool")))
                return
            self._raise_error("invalid boolean operand types", node.span.line, node.span.column)

        if node.operator == "not":
            value = self._pop_type(stack, node.span.line, node.span.column)
            if _is_named_type(value, "Bool"):
                stack.append(StackValue(_builtin_type("Bool")))
                return
            self._raise_error("invalid boolean operand types", node.span.line, node.span.column)

        raise NotImplementedError(f"operator checking not implemented for {node.operator}")

    def _check_if(
        self,
        node: IfNode,
        stack: list[TypeNode],
        local_types: dict[str, TypeNode],
    ) -> list[TypeNode]:
        condition_type = self._pop_type(stack, node.span.line, node.span.column)
        if not _is_named_type(condition_type, "Bool"):
            self._raise_error("if condition must be Bool", node.span.line, node.span.column)

        base_stack = list(stack)
        then_stack = self._check_block(node.then_block, list(base_stack), local_types)
        else_stack = self._check_block(node.else_block, list(base_stack), local_types)
        if not _same_stack(then_stack, else_stack):
            self._raise_error("if branches have incompatible stack effects", node.span.line, node.span.column)
        return then_stack

    def _check_case(
        self,
        node: CaseNode,
        stack: list[TypeNode],
        local_types: dict[str, TypeNode],
    ) -> list[TypeNode]:
        scrutinee_type = self._pop_type(stack, node.span.line, node.span.column)
        base_stack = list(stack)
        branch_stacks: list[list[TypeNode]] = []

        for branch in node.branches:
            branch_locals = dict(local_types)
            self._bind_case_pattern(branch.pattern, scrutinee_type, branch_locals)
            branch_stack = self._check_block(branch.body, list(base_stack), branch_locals)
            branch_stacks.append(branch_stack)

        if not branch_stacks:
            self._raise_error("case must have at least one branch", node.span.line, node.span.column)

        expected_stack = branch_stacks[0]
        for branch_stack in branch_stacks[1:]:
            if not _same_stack(branch_stack, expected_stack):
                self._raise_error(
                    "case branches have incompatible stack effects",
                    node.span.line,
                    node.span.column,
                )
        if not _is_case_exhaustive(node, scrutinee_type):
            self._raise_error("case is not exhaustive", node.span.line, node.span.column)
        return expected_stack

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
                )
            return

        if pattern.kind is PatternKind.NAME:
            if pattern.value not in {"MissingKey", "OutOfBounds"}:
                self._raise_error("unsupported case pattern", pattern.span.line, pattern.span.column)
            if not _is_valid_closed_variant_pattern(scrutinee_type, pattern.value):
                self._raise_error("case pattern does not match scrutinee type", pattern.span.line, pattern.span.column)
            return

        if pattern.kind in {PatternKind.OK, PatternKind.ERR}:
            if scrutinee_type.name != "Result" or len(scrutinee_type.args) != 2:
                self._raise_error(
                    "Ok/Err pattern requires Result scrutinee",
                    pattern.span.line,
                    pattern.span.column,
                )
            if pattern.kind is PatternKind.ERR and pattern.value is not None:
                if not _is_valid_result_error_variant(scrutinee_type, pattern.value):
                    self._raise_error(
                        "case pattern does not match scrutinee type",
                        pattern.span.line,
                        pattern.span.column,
                    )
            if pattern.binding is None:
                return
            branch_type = scrutinee_type.args[0] if pattern.kind is PatternKind.OK else scrutinee_type.args[1]
            if not isinstance(branch_type, TypeNode):
                self._raise_error("unsupported Result type argument", pattern.span.line, pattern.span.column)
            local_types[pattern.binding] = branch_type
            return

        self._raise_error("unsupported case pattern", pattern.span.line, pattern.span.column)

    def _check_quote(self, node: QuoteNode, stack: list[TypeNode]) -> list[TypeNode]:
        current_stack = list(stack)
        for parameter in reversed(node.captures):
            actual = self._pop_type(current_stack, node.span.line, node.span.column)
            if not _same_type(actual, parameter.type_node):
                self._raise_error("quotation capture types do not match", node.span.line, node.span.column)

        quote_locals = {parameter.name: parameter.type_node for parameter in node.captures}
        quote_locals.update({parameter.name: parameter.type_node for parameter in node.inputs})
        quote_end_stack = self._check_block(node.body, [], quote_locals)
        expected_outputs = [parameter.type_node for parameter in node.outputs]
        if not _same_stack(quote_end_stack, expected_outputs):
            self._raise_error("quotation body does not match declared outputs", node.span.line, node.span.column)

        quote_type = TypeNode(
            span=node.span,
            name="Quote",
            args=(
                QuoteTypeNode(
                    span=node.span,
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
                self._raise_error("list literal elements must have the same type", node.span.line, node.span.column)
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
        )
        if len(stack) != 1:
            self._raise_error("list literal element must produce exactly one value", element.span.line, element.span.column)
        return stack[0].type_node

    def _apply_signature(self, line: int, column: int, stack: list[TypeNode], inputs, outputs) -> None:
        for parameter in reversed(inputs):
            actual = self._pop_type(stack, line, column)
            if not _same_type(actual, parameter.type_node):
                self._raise_error("type mismatch in word call", line, column)
        for parameter in outputs:
            stack.append(StackValue(parameter.type_node))

    def _pop_value(self, stack, line: int, column: int) -> StackValue:
        if not stack:
            self._raise_error("insufficient stack", line, column)
        return stack.pop()

    def _pop_type(self, stack, line: int, column: int) -> TypeNode:
        return self._pop_value(stack, line, column).type_node

    def _raise_error(self, message: str, line: int, column: int) -> None:
        raise CheckerError(message=message, line=line, column=column)


def check(program: ProgramNode, symbols: SymbolTable) -> ProgramNode:
    return Checker(symbols).check(program)


def check_program(program: ProgramNode, symbols: SymbolTable) -> ProgramNode:
    return check(program, symbols)


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
    if type_node.name != "Quote" or len(type_node.args) != 1:
        return None
    signature = type_node.args[0]
    if not isinstance(signature, QuoteTypeNode):
        return None
    return signature


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
        _same_parameter_types(left.captures, right.captures)
        and _same_parameter_types(left.inputs, right.inputs)
        and _same_parameter_types(left.outputs, right.outputs)
    )


def _same_parameter_types(left, right) -> bool:
    if len(left) != len(right):
        return False
    return all(_same_type(left_parameter.type_node, right_parameter.type_node) for left_parameter, right_parameter in zip(left, right))


def _is_case_exhaustive(node: CaseNode, scrutinee_type: TypeNode) -> bool:
    patterns = [branch.pattern for branch in node.branches]
    if any(pattern.kind is PatternKind.WILDCARD for pattern in patterns):
        return True

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
