from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .ast_nodes import (
    ASTNode,
    AtomNode,
    BlockNode,
    CaseBranchNode,
    CaseNode,
    ExportDeclaration,
    IdentifierNode,
    ImportDeclaration,
    IncludeDeclaration,
    IfNode,
    LiteralKind,
    LiteralNode,
    ListLiteralNode,
    ModuleDeclaration,
    OperatorNode,
    ParameterNode,
    PatternKind,
    PatternNode,
    PropagateNode,
    ProgramNode,
    QualifiedModuleName,
    QuoteEffect,
    QuoteNode,
    ResultErrNode,
    ResultOkNode,
    QuoteTypeNode,
    SignatureNode,
    TypedEmptyListNode,
    TypedEmptyMapNode,
    TypeNode,
    Visibility,
    WordDefNode,
)
from .tokens import SourceSpan, Token, TokenKind

__all__ = ["ParseError", "Parser"]

_PRIMITIVE_OPERATOR_NAMES = {
    "call",
    "dup",
    "drop",
    "swap",
    "over",
    "rot",
    "div",
    "mod",
    "and",
    "or",
    "not",
}

_ERR_VARIANT_PATTERN_NAMES = {"MissingKey", "OutOfBounds"}
_RESERVED_WORD_NAMES = {
    "call",
    "dirty",
    "MissingKey",
    "OutOfBounds",
}
_RESERVED_WORD_PREFIXES = (
    "result.",
    "list.",
    "map.",
    "host.",
)


@dataclass(slots=True)
class ParseError(Exception):
    message: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.message} at {self.line}:{self.column}"


class Parser:
    def __init__(self, tokens: Sequence[Token]) -> None:
        self._tokens = list(tokens)
        if not self._tokens or self._tokens[-1].kind is not TokenKind.EOF:
            span = self._tokens[-1].span if self._tokens else SourceSpan(1, 1, 0)
            self._tokens.append(Token(TokenKind.EOF, "", span))
        self._index = 0

    def parse(self) -> ProgramNode:
        declarations: list[ASTNode] = []
        words: list[WordDefNode] = []

        while not self._check(TokenKind.EOF):
            declaration = self._parse_top_level_declaration()
            declarations.append(declaration)
            if isinstance(declaration, ModuleDeclaration):
                words.extend(
                    item for item in declaration.items if isinstance(item, WordDefNode)
                )

        eof_token = self._current()
        if declarations:
            span = self._span_from(declarations[0], eof_token)
        else:
            span = eof_token.span

        return ProgramNode(
            span=span,
            words=tuple(words),
            declarations=tuple(declarations),
        )

    def _parse_top_level_declaration(self) -> ASTNode:
        if self._check(TokenKind.MODULE):
            return self._parse_module_declaration()
        if self._check(TokenKind.IMPORT):
            return self._parse_import_declaration()
        if self._check(TokenKind.INCLUDE):
            return self._parse_include_declaration()
        if self._check(TokenKind.EXPORT):
            self._raise_error("export declaration is only allowed inside module")
        if self._is_word_def_start():
            self._raise_error("top-level word definition is not allowed")
        self._raise_error("unexpected token")

    def _parse_module_declaration(self) -> ModuleDeclaration:
        start = self._expect(TokenKind.MODULE, "expected 'module'")
        module_name = self._parse_qualified_module_name("expected module name")
        items: list[ASTNode] = []

        while not self._check(TokenKind.END_MODULE):
            if self._check(TokenKind.EOF):
                self._raise_error("missing 'end-module'")
            if self._check(TokenKind.MODULE):
                self._raise_error("nested module declaration is not allowed")
            if self._check(TokenKind.IMPORT) or self._check(TokenKind.INCLUDE):
                self._raise_error("unexpected token")
            if self._check(TokenKind.EXPORT):
                items.append(self._parse_export_declaration())
                continue
            if self._is_word_def_start():
                items.append(self._parse_word_def(is_top_level=False))
                continue
            self._raise_error("unexpected token")

        end = self._expect(TokenKind.END_MODULE, "missing 'end-module'")
        return ModuleDeclaration(
            span=self._span_from(start, end),
            name=module_name,
            items=tuple(items),
        )

    def _parse_import_declaration(self) -> ImportDeclaration:
        start = self._expect(TokenKind.IMPORT, "expected 'import'")
        target = self._parse_qualified_module_name("expected import target")
        alias: str | None = None
        end: Token | QualifiedModuleName = target
        if self._check(TokenKind.IDENTIFIER) and self._current().lexeme == "as":
            self._advance()
            alias_token = self._expect(TokenKind.IDENTIFIER, "expected alias after 'as'")
            alias = alias_token.lexeme
            end = alias_token
        return ImportDeclaration(span=self._span_from(start, end), target=target, alias=alias)

    def _parse_include_declaration(self) -> IncludeDeclaration:
        start = self._expect(TokenKind.INCLUDE, "expected 'include'")
        path_token = self._expect(TokenKind.STRING_LITERAL, "expected include path string")
        return IncludeDeclaration(span=self._span_from(start, path_token), path=path_token.lexeme)

    def _parse_export_declaration(self) -> ExportDeclaration:
        start = self._expect(TokenKind.EXPORT, "expected 'export'")
        self._expect(TokenKind.COLON, "expected ':' after export")
        word_token = self._expect_definition_identifier("expected exported word name")
        if "." in word_token.lexeme:
            self._raise_error("export declaration expects local word name")
        return ExportDeclaration(span=self._span_from(start, word_token), word_name=word_token.lexeme)

    def _parse_qualified_module_name(self, message: str) -> QualifiedModuleName:
        token = self._expect(TokenKind.QUALIFIED_MODULE_NAME, message)
        parts = tuple(token.lexeme[1:].split("."))
        return QualifiedModuleName(span=token.span, parts=parts)

    def _parse_word_def(self, *, is_top_level: bool) -> WordDefNode:
        start = self._current()
        visibility = Visibility.PRIVATE
        is_dirty_annotation = False

        if self._match(TokenKind.PUB):
            visibility = Visibility.PUB
            if self._match(TokenKind.DIRTY):
                is_dirty_annotation = True
            self._expect(TokenKind.COLON, "expected ':' after pub")
        elif self._match(TokenKind.DIRTY):
            is_dirty_annotation = True
            self._expect(TokenKind.COLON, "expected ':' after dirty")
        else:
            self._expect(TokenKind.COLON, "expected ':'")

        name_token = self._expect_definition_identifier("expected word name")
        self._validate_user_word_name(name_token)
        signature = self._parse_signature()
        nested_words: list[WordDefNode] = []
        body = self._parse_block(
            stop_kinds={TokenKind.SEMICOLON},
            nested_words=nested_words,
            allow_nested_defs=True,
        )
        end = self._expect(TokenKind.SEMICOLON, "missing ';'")
        return WordDefNode(
            span=self._span_from(start, end),
            name=name_token.lexeme,
            signature=signature,
            body=body,
            visibility=visibility,
            is_dirty_annotation=is_dirty_annotation,
            nested_words=tuple(nested_words),
        )

    def _span_from(self, start: Token | ASTNode | SourceSpan, end: Token | ASTNode | SourceSpan) -> SourceSpan:
        start_span = self._as_span(start)
        end_span = self._as_span(end)
        if start_span.source != end_span.source:
            raise ValueError("cannot combine spans from different sources")
        return SourceSpan(
            source=start_span.source,
            start=start_span.start,
            end=end_span.end,
        )

    @staticmethod
    def _as_span(value: Token | ASTNode | SourceSpan) -> SourceSpan:
        if isinstance(value, SourceSpan):
            return value
        if isinstance(value, Token):
            return value.span
        if isinstance(value, ASTNode):
            return value.span
        raise TypeError("value must expose a span")

    def _parse_signature(self) -> SignatureNode:
        start = self._expect(TokenKind.LBRACE, "expected '{' to start signature")
        inputs = self._parse_parameters_until(TokenKind.STACK_ARROW)
        self._ensure_unique_parameter_names(inputs, "duplicate local name in word frame")
        self._expect(TokenKind.STACK_ARROW, "expected '--' in signature")
        outputs = self._parse_parameters_until(TokenKind.RBRACE)
        end = self._expect(TokenKind.RBRACE, "expected '}' to end signature")
        return SignatureNode(span=self._span_from(start, end), inputs=tuple(inputs), outputs=tuple(outputs))

    def _parse_parameters_until(self, terminator: TokenKind) -> list[ParameterNode]:
        params: list[ParameterNode] = []
        if self._check(terminator):
            return params
        while not self._check(terminator):
            if self._check(TokenKind.EOF):
                self._raise_error("unexpected end of input")
            params.append(self._parse_parameter())
        return params

    def _parse_parameter(self) -> ParameterNode:
        name_token = self._expect_definition_identifier("expected parameter name")
        self._expect(TokenKind.COLON, "expected ':' in parameter")
        type_node = self._parse_type()
        return ParameterNode(span=name_token.span, name=name_token.lexeme, type_node=type_node)

    def _expect_definition_identifier(self, message: str) -> Token:
        token = self._current()
        if token.kind is TokenKind.DIRTY:
            raise ParseError(
                message="cannot define reserved identifier: dirty",
                line=token.span.line,
                column=token.span.column,
            )
        return self._expect(TokenKind.IDENTIFIER, message)

    def _parse_type(self) -> TypeNode | QuoteTypeNode:
        name_token = self._expect(TokenKind.IDENTIFIER, "malformed type")

        if name_token.lexeme in {"Quote", "DirtyQuote"} and self._match(TokenKind.LT):
            if self._check(TokenKind.LBRACE):
                quote_type = self._parse_quote_type()
                self._expect(TokenKind.GT, "malformed type")
                quote_type.effect_kind = (
                    QuoteEffect.DIRTY
                    if name_token.lexeme == "DirtyQuote"
                    else QuoteEffect.PURE
                )
                return TypeNode(
                    span=name_token.span,
                    name="Quote",
                    args=(quote_type,),
                )

        if self._match(TokenKind.LT):
            args = self._parse_type_arguments()
            return TypeNode(span=name_token.span, name=name_token.lexeme, args=tuple(args))

        return TypeNode(span=name_token.span, name=name_token.lexeme)

    def _parse_type_arguments(self) -> list[TypeNode | QuoteTypeNode]:
        args: list[TypeNode | QuoteTypeNode] = []
        if self._check(TokenKind.GT):
            self._raise_error("malformed type")
        while True:
            args.append(self._parse_type())
            if self._match(TokenKind.COMMA):
                continue
            self._expect(TokenKind.GT, "malformed type")
            return args

    def _parse_quote_type(self) -> QuoteTypeNode:
        start = self._expect(TokenKind.LBRACE, "malformed type")
        captures = self._parse_parameters_until(TokenKind.BAR)
        self._ensure_unique_parameter_names(captures, "duplicate local name in quotation frame")
        self._expect(TokenKind.BAR, "malformed type")
        inputs = self._parse_parameters_until(TokenKind.STACK_ARROW)
        self._ensure_unique_parameter_names(
            captures + inputs,
            "duplicate local name in quotation frame",
        )
        self._expect(TokenKind.STACK_ARROW, "malformed type")
        outputs = self._parse_parameters_until(TokenKind.RBRACE)
        end = self._expect(TokenKind.RBRACE, "malformed type")
        return QuoteTypeNode(
            span=self._span_from(start, end),
            captures=tuple(captures),
            inputs=tuple(inputs),
            outputs=tuple(outputs),
        )

    def _parse_block(
        self,
        *,
        stop_kinds: set[TokenKind],
        nested_words: list[WordDefNode] | None,
        allow_nested_defs: bool,
        stop_predicate: Callable[[], bool] | None = None,
    ) -> BlockNode:
        items: list[AtomNode] = []
        while not self._check(TokenKind.EOF):
            if stop_predicate is not None and stop_predicate():
                break
            if self._check_any(stop_kinds):
                break
            if self._is_word_def_start():
                if not allow_nested_defs:
                    self._raise_error("unexpected nested word definition")
                nested_word = self._parse_word_def(is_top_level=False)
                if nested_words is not None:
                    nested_words.append(nested_word)
                continue
            items.append(self._parse_atom(nested_words=nested_words))

        if items:
            span = self._span_from(items[0], items[-1])
        else:
            boundary_span = self._current().span
            span = SourceSpan(
                source=boundary_span.source,
                start=boundary_span.start,
                end=boundary_span.start,
            )

        return BlockNode(span=span, items=tuple(items))

    def _parse_atom(self, *, nested_words: list[WordDefNode] | None) -> AtomNode:
        token = self._current()

        if token.kind is TokenKind.QUALIFIED_MODULE_NAME:
            if "." not in token.lexeme:
                self._raise_error(
                    "qualified module reference in expression requires a word segment"
                )
            self._advance()
            return IdentifierNode(span=token.span, name=token.lexeme)

        if token.kind is TokenKind.IDENTIFIER:
            if token.lexeme == "map.empty":
                return self._parse_typed_empty_map()
            self._advance()
            if token.lexeme in _PRIMITIVE_OPERATOR_NAMES:
                return OperatorNode(span=token.span, operator=token.lexeme)
            return IdentifierNode(span=token.span, name=token.lexeme)

        if token.kind is TokenKind.OPERATOR:
            self._advance()
            return OperatorNode(span=token.span, operator=token.lexeme)

        if token.kind is TokenKind.LT:
            self._advance()
            return OperatorNode(span=token.span, operator="<")

        if token.kind is TokenKind.GT:
            self._advance()
            return OperatorNode(span=token.span, operator=">")

        if token.kind is TokenKind.INT_LITERAL:
            self._advance()
            return LiteralNode(
                span=token.span,
                kind=LiteralKind.INT,
                value=int(token.lexeme),
                raw=token.lexeme,
            )

        if token.kind is TokenKind.FLOAT_LITERAL:
            self._advance()
            return LiteralNode(
                span=token.span,
                kind=LiteralKind.FLOAT,
                value=float(token.lexeme),
                raw=token.lexeme,
            )

        if token.kind is TokenKind.STRING_LITERAL:
            self._advance()
            return LiteralNode(
                span=token.span,
                kind=LiteralKind.STRING,
                value=token.lexeme,
                raw=token.lexeme,
            )

        if token.kind is TokenKind.BOOL_LITERAL:
            self._advance()
            value = token.lexeme == "true"
            return LiteralNode(
                span=token.span,
                kind=LiteralKind.BOOL,
                value=value,
                raw=token.lexeme,
            )

        if token.kind is TokenKind.RESULT_OK:
            self._advance()
            return ResultOkNode(span=token.span)

        if token.kind is TokenKind.RESULT_ERR:
            self._advance()
            return ResultErrNode(span=token.span)

        if token.kind is TokenKind.PROPAGATE:
            self._advance()
            return PropagateNode(span=token.span)

        if token.kind is TokenKind.LBRACKET:
            return self._parse_list_literal(nested_words=nested_words)

        if token.kind is TokenKind.QUOTE_START:
            return self._parse_quote(nested_words=nested_words)

        if token.kind is TokenKind.IF:
            return self._parse_if(nested_words=nested_words)

        if token.kind is TokenKind.CASE:
            return self._parse_case(nested_words=nested_words)

        self._raise_error("unexpected token")

    def _parse_list_literal(self, *, nested_words: list[WordDefNode] | None) -> AtomNode:
        start = self._expect(TokenKind.LBRACKET, "expected '['")
        elements: list[AtomNode] = []
        if self._check(TokenKind.RBRACKET):
            end = self._expect(TokenKind.RBRACKET, "expected ']'")
            self._expect(TokenKind.COLON, "empty list requires explicit type annotation")
            type_node = self._parse_type()
            if type_node.name != "List":
                self._raise_error("empty list requires List<T> annotation")
            return TypedEmptyListNode(span=self._span_from(start, end), type_node=type_node)

        while True:
            elements.append(self._parse_list_element(nested_words=nested_words))
            if self._match(TokenKind.COMMA):
                continue
            end = self._expect(TokenKind.RBRACKET, "expected ']'")
            return ListLiteralNode(span=self._span_from(start, end), elements=tuple(elements))

    def _parse_typed_empty_map(self) -> TypedEmptyMapNode:
        start = self._expect(TokenKind.IDENTIFIER, "expected 'map.empty'")
        if start.lexeme != "map.empty":
            self._raise_error("unexpected token")
        self._expect(TokenKind.COLON, "map.empty requires explicit type annotation")
        type_node = self._parse_type()
        if type_node.name != "Map":
            self._raise_error("map.empty requires Map<K,V> annotation")
        return TypedEmptyMapNode(span=start.span, type_node=type_node)

    def _parse_list_element(self, *, nested_words: list[WordDefNode] | None) -> AtomNode:
        token = self._current()
        if token.kind in {
            TokenKind.IDENTIFIER,
            TokenKind.OPERATOR,
            TokenKind.LT,
            TokenKind.GT,
            TokenKind.INT_LITERAL,
            TokenKind.FLOAT_LITERAL,
            TokenKind.STRING_LITERAL,
            TokenKind.BOOL_LITERAL,
        }:
            return self._parse_atom(nested_words=nested_words)
        if token.kind is TokenKind.LBRACKET:
            return self._parse_list_literal(nested_words=nested_words)
        if token.kind is TokenKind.QUOTE_START:
            return self._parse_quote(nested_words=nested_words)
        self._raise_error("unexpected token")

    def _parse_quote(self, *, nested_words: list[WordDefNode] | None) -> QuoteNode:
        start = self._expect(TokenKind.QUOTE_START, "expected ':[ '")
        captures = self._parse_parameters_until(TokenKind.BAR)
        self._ensure_unique_parameter_names(captures, "duplicate local name in quotation frame")
        self._expect(TokenKind.BAR, "malformed quotation")
        inputs = self._parse_parameters_until(TokenKind.STACK_ARROW)
        self._ensure_unique_parameter_names(
            captures + inputs,
            "duplicate local name in quotation frame",
        )
        self._expect(TokenKind.STACK_ARROW, "malformed quotation")
        outputs = self._parse_parameters_until(TokenKind.BAR)
        self._expect(TokenKind.BAR, "malformed quotation")
        body = self._parse_block(
            stop_kinds={TokenKind.QUOTE_END},
            nested_words=nested_words,
            allow_nested_defs=False,
        )
        end = self._expect(TokenKind.QUOTE_END, "malformed quotation")
        return QuoteNode(
            span=self._span_from(start, end),
            body=body,
            captures=tuple(captures),
            inputs=tuple(inputs),
            outputs=tuple(outputs),
        )

    def _parse_if(self, *, nested_words: list[WordDefNode] | None) -> IfNode:
        start = self._expect(TokenKind.IF, "expected 'if'")
        then_block = self._parse_block(
            stop_kinds={TokenKind.ELSE},
            nested_words=nested_words,
            allow_nested_defs=False,
        )
        self._expect(TokenKind.ELSE, "missing 'else'")
        else_block = self._parse_block(
            stop_kinds={TokenKind.END},
            nested_words=nested_words,
            allow_nested_defs=False,
        )
        end = self._expect(TokenKind.END, "missing 'end'")
        return IfNode(
            span=self._span_from(start, end),
            then_block=then_block,
            else_block=else_block,
        )

    def _parse_case(self, *, nested_words: list[WordDefNode] | None) -> CaseNode:
        start = self._expect(TokenKind.CASE, "expected 'case'")
        branches: list[CaseBranchNode] = []

        while not self._check(TokenKind.END):
            if self._check(TokenKind.EOF):
                self._raise_error("missing 'end'")
            branches.append(self._parse_case_branch(nested_words=nested_words))

        self._expect(TokenKind.END, "missing 'end'")
        return CaseNode(span=start.span, branches=tuple(branches))

    def _parse_case_branch(self, *, nested_words: list[WordDefNode] | None) -> CaseBranchNode:
        pattern = self._parse_pattern()
        guard: BlockNode | None = None
        if self._match(TokenKind.WHEN):
            guard = self._parse_block(
                stop_kinds={TokenKind.CASE_ARROW},
                nested_words=None,
                allow_nested_defs=False,
                stop_predicate=lambda: self._check(TokenKind.CASE_ARROW),
            )
        self._expect(TokenKind.CASE_ARROW, "missing '=>'")

        body = self._parse_block(
            stop_kinds={TokenKind.END},
            nested_words=nested_words,
            allow_nested_defs=False,
            stop_predicate=lambda: self._check(TokenKind.END)
            or self._looks_like_case_branch_start_at_current(),
        )
        return CaseBranchNode(span=pattern.span, pattern=pattern, body=body, guard=guard)

    def _parse_pattern(self) -> PatternNode:
        pattern, next_index = self._parse_pattern_at(self._index)
        self._index = next_index
        return pattern

    def _parse_pattern_at(self, index: int) -> tuple[PatternNode, int]:
        token = self._tokens[index]

        if token.kind is TokenKind.UNDERSCORE:
            return (
                PatternNode(span=token.span, kind=PatternKind.WILDCARD, value=None, binding=None),
                index + 1,
            )

        if token.kind in {
            TokenKind.INT_LITERAL,
            TokenKind.STRING_LITERAL,
            TokenKind.BOOL_LITERAL,
        }:
            return (
                PatternNode(
                    span=token.span,
                    kind=PatternKind.LITERAL,
                    value=self._literal_value(token),
                    binding=None,
                ),
                index + 1,
            )

        if token.kind is TokenKind.IDENTIFIER:
            if token.lexeme in {"MissingKey", "OutOfBounds"}:
                return (
                    PatternNode(
                        span=token.span,
                        kind=PatternKind.NAME,
                        value=token.lexeme,
                        binding=None,
                    ),
                    index + 1,
                )
            if index + 1 < len(self._tokens) and self._tokens[index + 1].kind is TokenKind.LPAREN:
                if token.lexeme in {"Ok", "Err"}:
                    return self._parse_constructor_pattern(token, index)
            self._raise_error("unexpected token")

        self._raise_error("unexpected token")

    def _parse_constructor_pattern(self, token: Token, index: int) -> tuple[PatternNode, int]:
        inner_index = index + 2
        if inner_index >= len(self._tokens):
            self._raise_error("unexpected end of input")

        binding_token = self._tokens[inner_index]
        if binding_token.kind is not TokenKind.IDENTIFIER:
            self._raise_error("unexpected token")

        close_index = inner_index + 1
        if close_index >= len(self._tokens) or self._tokens[close_index].kind is not TokenKind.RPAREN:
            self._raise_error("unexpected token")

        kind = PatternKind.OK if token.lexeme == "Ok" else PatternKind.ERR
        value = None
        binding = binding_token.lexeme
        if kind is PatternKind.ERR and binding_token.lexeme in _ERR_VARIANT_PATTERN_NAMES:
            value = binding_token.lexeme
            binding = None

        return (
            PatternNode(
                span=token.span,
                kind=kind,
                value=value,
                binding=binding,
            ),
            close_index + 1,
        )

    def _looks_like_case_branch_start_at_current(self) -> bool:
        try:
            _, next_index = self._parse_pattern_at(self._index)
        except ParseError:
            return False
        if self._tokens[next_index].kind is TokenKind.CASE_ARROW:
            return True
        if self._tokens[next_index].kind is TokenKind.WHEN:
            return True
        return False

    def _literal_value(self, token: Token) -> object:
        if token.kind is TokenKind.INT_LITERAL:
            return int(token.lexeme)
        if token.kind is TokenKind.FLOAT_LITERAL:
            return float(token.lexeme)
        if token.kind is TokenKind.BOOL_LITERAL:
            return token.lexeme == "true"
        return token.lexeme

    def _is_word_def_start(self) -> bool:
        token = self._current()
        if token.kind in {TokenKind.PUB, TokenKind.DIRTY}:
            return True
        return token.kind is TokenKind.COLON

    def _ensure_unique_parameter_names(
        self,
        params: list[ParameterNode],
        message: str,
    ) -> None:
        seen: set[str] = set()
        for param in params:
            if param.name in seen:
                raise ParseError(message=message, line=param.span.line, column=param.span.column)
            seen.add(param.name)

    def _check(self, kind: TokenKind) -> bool:
        return self._current().kind is kind

    def _check_any(self, kinds: set[TokenKind]) -> bool:
        return self._current().kind in kinds

    def _match(self, kind: TokenKind) -> bool:
        if self._check(kind):
            self._advance()
            return True
        return False

    def _expect(self, kind: TokenKind, message: str) -> Token:
        token = self._current()
        if token.kind is not kind:
            self._raise_error(message)
        self._advance()
        return token

    def _current(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        if self._index < len(self._tokens) - 1:
            self._index += 1
        return token

    def _raise_error(self, message: str) -> None:
        token = self._current()
        raise ParseError(message=message, line=token.span.line, column=token.span.column)

    def _validate_user_word_name(self, token: Token) -> None:
        lexeme = token.lexeme
        if lexeme in _RESERVED_WORD_NAMES:
            raise ParseError(
                message=f"cannot define reserved word: {lexeme}",
                line=token.span.line,
                column=token.span.column,
            )
        for prefix in _RESERVED_WORD_PREFIXES:
            if lexeme.startswith(prefix):
                raise ParseError(
                    message=f"cannot define reserved namespace word: {lexeme}",
                    line=token.span.line,
                    column=token.span.column,
                )
        if "." in lexeme:
            raise ParseError(
                message=f"cannot define qualified word name: {lexeme}",
                line=token.span.line,
                column=token.span.column,
            )
