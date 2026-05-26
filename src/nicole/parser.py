from __future__ import annotations

from typing import Callable, Sequence

from .ast_nodes import (
    ASTNode,
    AtomNode,
    BlockNode,
    CaseBranchNode,
    CaseNode,
    ExportDeclaration,
    HostAbiEffect,
    HostOpaqueDeclaration,
    HostPathNode,
    HostRequireDeclaration,
    IdentifierNode,
    ImportAliasKind,
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
from .errors import DiagnosticError, DiagnosticPhase
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

_PARSER_ERROR_DETAILS: dict[str, tuple[str, str | None]] = {
    "imports are only allowed inside modules": (
        "PARSER_TOP_LEVEL_IMPORT_FORBIDDEN",
        "move this import to the beginning of a module",
    ),
    "imports must appear before module definitions": (
        "PARSER_IMPORT_ORDER",
        "move this import before the first module definition",
    ),
    "host ABI declarations are only allowed inside module @host": (
        "PARSER_HOST_DECLARATION_OUTSIDE_HOST_MODULE",
        "move this declaration into module @host",
    ),
    "module @host only allows require and opaque declarations": (
        "PARSER_HOST_MODULE_INVALID_CONTENT",
        "remove this declaration or move it to a normal module",
    ),
    "host ABI paths are relative to @host": (
        "PARSER_HOST_PATH_MUST_BE_RELATIVE",
        "remove the @host. prefix",
    ),
    "expected host ABI path": (
        "PARSER_EXPECTED_HOST_PATH",
        "use a relative host path such as console.log or io.FileHandle",
    ),
    "host requirement must declare an effect": (
        "PARSER_HOST_REQUIRE_MISSING_EFFECT",
        "add pure or dirty after the signature",
    ),
    "grouped import must list at least one member": (
        "PARSER_GROUPED_IMPORT_EMPTY",
        "add imported member names inside the braces",
    ),
    "grouped import requires an alias": (
        "PARSER_GROUPED_IMPORT_ALIAS_REQUIRED",
        "add as <alias> or as * after the grouped import",
    ),
    "expected grouped import alias": (
        "PARSER_GROUPED_IMPORT_ALIAS_INVALID",
        "use as <alias> or as *",
    ),
    "export declaration is only allowed inside module": (
        "PARSER_EXPORT_OUTSIDE_MODULE",
        "move this export declaration inside a module block",
    ),
    "top-level word definition is not allowed": (
        "PARSER_TOP_LEVEL_WORD_DEF",
        "wrap this definition in a 'module ... end-module' block",
    ),
    "unexpected token": ("PARSER_UNEXPECTED_TOKEN", None),
    "expected 'module'": ("PARSER_EXPECTED_MODULE_KEYWORD", "start with the 'module' keyword"),
    "missing 'end-module'": ("PARSER_MISSING_END_MODULE", "add 'end-module' to close the module"),
    "expected module name": ("PARSER_EXPECTED_MODULE_NAME", "use a module name such as @app"),
    "nested module declaration is not allowed": (
        "PARSER_NESTED_MODULE_DECLARATION",
        "move nested modules to top-level declarations",
    ),
    "expected 'import'": ("PARSER_EXPECTED_IMPORT_KEYWORD", "start this declaration with 'import'"),
    "expected import target": ("PARSER_EXPECTED_IMPORT_TARGET", "provide a target such as @math"),
    "expected alias after 'as'": ("PARSER_EXPECTED_IMPORT_ALIAS", "add an identifier after 'as'"),
    "expected 'include'": ("PARSER_EXPECTED_INCLUDE_KEYWORD", "start this declaration with 'include'"),
    "expected include path string": ("PARSER_EXPECTED_INCLUDE_PATH", "provide a quoted include path"),
    "expected 'export'": ("PARSER_EXPECTED_EXPORT_KEYWORD", "start this declaration with 'export'"),
    "expected ':' after export": ("PARSER_EXPECTED_EXPORT_COLON", "add ':' after 'export'"),
    "expected exported word name": ("PARSER_EXPECTED_EXPORTED_WORD_NAME", "provide a local word name"),
    "export declaration expects local word name": (
        "PARSER_EXPORT_EXPECTS_LOCAL_WORD",
        "export by local word name only",
    ),
    "expected ':' after pub": ("PARSER_EXPECTED_COLON_AFTER_PUB", "add ':' after 'pub'"),
    "expected ':' after dirty": ("PARSER_EXPECTED_COLON_AFTER_DIRTY", "add ':' after 'dirty'"),
    "expected ':'": ("PARSER_EXPECTED_WORD_DEF_COLON", "add ':' before the word name"),
    "expected word name": ("PARSER_EXPECTED_WORD_NAME", "provide a word identifier"),
    "missing ';'": ("PARSER_MISSING_SEMICOLON", "terminate the definition with ';'"),
    "expected '{' to start signature": (
        "PARSER_EXPECTED_SIGNATURE_START",
        "start the signature with '{'",
    ),
    "duplicate local name in word frame": (
        "PARSER_DUPLICATE_LOCAL_NAME",
        "rename one of the duplicate local names",
    ),
    "expected '--' in signature": (
        "PARSER_EXPECTED_STACK_ARROW",
        "separate inputs and outputs with '--'",
    ),
    "expected '}' to end signature": ("PARSER_EXPECTED_SIGNATURE_END", "close the signature with '}'"),
    "unexpected end of input": ("PARSER_UNEXPECTED_EOF", "complete the incomplete declaration or expression"),
    "expected parameter name": ("PARSER_EXPECTED_PARAMETER_NAME", "add a parameter name"),
    "expected ':' in parameter": ("PARSER_EXPECTED_PARAMETER_COLON", "add ':' between name and type"),
    "cannot define reserved identifier: dirty": (
        "PARSER_RESERVED_IDENTIFIER",
        "rename this identifier to a non-reserved name",
    ),
    "malformed type": ("PARSER_INVALID_TYPE", "use a valid type such as Int or List<Int>"),
    "unexpected nested word definition": (
        "PARSER_UNEXPECTED_NESTED_WORD_DEF",
        "move nested definitions out of this control-flow block",
    ),
    "qualified module reference in expression requires a word segment": (
        "PARSER_BARE_MODULE_REFERENCE",
        "use '@module.word' in expressions",
    ),
    "expected '['": ("PARSER_EXPECTED_LIST_START", "start list literals with '['"),
    "expected ']'": ("PARSER_EXPECTED_LIST_END", "close list literals with ']'"),
    "empty list requires explicit type annotation": (
        "PARSER_MISSING_EMPTY_LIST_ANNOTATION",
        "add a ':List<T>' type annotation after '[]'",
    ),
    "empty list requires List<T> annotation": (
        "PARSER_INVALID_EMPTY_LIST_ANNOTATION",
        "use a List<T> annotation for empty list literals",
    ),
    "expected 'map.empty'": ("PARSER_EXPECTED_MAP_EMPTY", "use the 'map.empty' literal form"),
    "map.empty requires explicit type annotation": (
        "PARSER_MISSING_EMPTY_MAP_ANNOTATION",
        "add a ':Map<K,V>' type annotation after map.empty",
    ),
    "map.empty requires Map<K,V> annotation": (
        "PARSER_INVALID_EMPTY_MAP_ANNOTATION",
        "use a Map<K,V> annotation for map.empty",
    ),
    "expected ':[ '": ("PARSER_EXPECTED_QUOTE_START", "start quotations with ':[ '"),
    "malformed quotation": ("PARSER_MALFORMED_QUOTATION", "fix quotation syntax and close it with ';]'"),
    "expected 'if'": ("PARSER_EXPECTED_IF", "start this branch with 'if'"),
    "missing 'else'": ("PARSER_MISSING_ELSE", "add the 'else' branch"),
    "missing 'end'": ("PARSER_MISSING_END", "add 'end' to close this block"),
    "expected 'case'": ("PARSER_EXPECTED_CASE", "start this branch with 'case'"),
    "missing '=>'": ("PARSER_MISSING_CASE_ARROW", "add '=>' between pattern and branch body"),
}

_DEFINITION_IDENTIFIER_ERROR_CODES: dict[str, str] = {
    "expected exported word name": "PARSER_EXPECTED_EXPORTED_WORD_NAME",
    "expected word name": "PARSER_EXPECTED_WORD_NAME",
    "expected parameter name": "PARSER_EXPECTED_PARAMETER_NAME",
}

_QUALIFIED_MODULE_NAME_ERROR_CODES: dict[str, str] = {
    "expected module name": "PARSER_EXPECTED_MODULE_NAME",
    "expected import target": "PARSER_EXPECTED_IMPORT_TARGET",
}


class ParseError(DiagnosticError):
    phase = DiagnosticPhase.PARSER
    default_code = "PARSER_ERROR"


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
            self._raise_error("imports are only allowed inside modules")
        if self._check(TokenKind.REQUIRE) or self._check(TokenKind.OPAQUE):
            self._raise_error("host ABI declarations are only allowed inside module @host")
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
        is_host_module = module_name.parts == ("host",)
        items: list[ASTNode] = []

        if is_host_module:
            while not self._check(TokenKind.END_MODULE):
                if self._check(TokenKind.EOF):
                    self._raise_error("missing 'end-module'")
                if self._check(TokenKind.MODULE):
                    self._raise_error("nested module declaration is not allowed")
                if self._check(TokenKind.REQUIRE):
                    items.append(self._parse_host_require_declaration())
                    continue
                if self._check(TokenKind.OPAQUE):
                    items.append(self._parse_host_opaque_declaration())
                    continue
                self._raise_error("module @host only allows require and opaque declarations")
        else:
            while self._check(TokenKind.IMPORT):
                items.append(self._parse_import_declaration())

        while not self._check(TokenKind.END_MODULE):
            if self._check(TokenKind.EOF):
                self._raise_error("missing 'end-module'")
            if self._check(TokenKind.MODULE):
                self._raise_error("nested module declaration is not allowed")
            if self._check(TokenKind.IMPORT):
                self._raise_error("imports must appear before module definitions")
            if self._check(TokenKind.INCLUDE):
                self._raise_error("unexpected token")
            if self._check(TokenKind.REQUIRE) or self._check(TokenKind.OPAQUE):
                self._raise_error("host ABI declarations are only allowed inside module @host")
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
            is_host_module=is_host_module,
        )

    def _parse_import_declaration(self) -> ImportDeclaration:
        start = self._expect(TokenKind.IMPORT, "expected 'import'")
        if self._check(TokenKind.QUALIFIED_MODULE_PREFIX):
            return self._parse_grouped_import_declaration(start)

        target = self._parse_qualified_module_name("expected import target")
        alias: str | None = None
        end: Token | QualifiedModuleName = target
        if self._check(TokenKind.IDENTIFIER) and self._current().lexeme == "as":
            self._advance()
            alias_token = self._expect(TokenKind.IDENTIFIER, "expected alias after 'as'")
            alias = alias_token.lexeme
            end = alias_token
        return ImportDeclaration(span=self._span_from(start, end), target=target, alias=alias)

    def _parse_grouped_import_declaration(self, start: Token) -> ImportDeclaration:
        prefix_token = self._expect(TokenKind.QUALIFIED_MODULE_PREFIX, "expected import target")
        prefix_parts = tuple(prefix_token.lexeme[1:-1].split("."))
        target = QualifiedModuleName(span=prefix_token.span, parts=prefix_parts)

        self._expect(TokenKind.LBRACE, "unexpected token")
        if self._check(TokenKind.RBRACE):
            self._raise_error("grouped import must list at least one member")

        members: list[str] = []
        closing_brace_token: Token | None = None
        while True:
            member_token = self._expect(TokenKind.IDENTIFIER, "unexpected token")
            members.append(member_token.lexeme)
            if self._check(TokenKind.RBRACE):
                closing_brace_token = self._advance()
                break

        if not (self._check(TokenKind.IDENTIFIER) and self._current().lexeme == "as"):
            self._raise_error(
                "grouped import requires an alias",
                span=closing_brace_token.span if closing_brace_token is not None else None,
            )
        as_token = self._advance()

        if self._check(TokenKind.OPERATOR) and self._current().lexeme == "*":
            star_token = self._advance()
            return ImportDeclaration(
                span=self._span_from(start, star_token),
                target=target,
                alias=None,
                is_grouped=True,
                grouped_members=tuple(members),
                alias_kind=ImportAliasKind.STAR,
            )

        if self._check(TokenKind.IDENTIFIER):
            alias_token = self._advance()
            return ImportDeclaration(
                span=self._span_from(start, alias_token),
                target=target,
                alias=alias_token.lexeme,
                is_grouped=True,
                grouped_members=tuple(members),
                alias_kind=ImportAliasKind.PREFIX,
            )

        if self._check(TokenKind.END_MODULE) or self._check(TokenKind.EOF):
            self._raise_error("expected grouped import alias", span=as_token.span)
        self._raise_error("expected grouped import alias", span=self._current().span)

    def _parse_include_declaration(self) -> IncludeDeclaration:
        start = self._expect(TokenKind.INCLUDE, "expected 'include'")
        path_token = self._expect(TokenKind.STRING_LITERAL, "expected include path string")
        return IncludeDeclaration(span=self._span_from(start, path_token), path=path_token.lexeme)

    def _parse_export_declaration(self) -> ExportDeclaration:
        start = self._expect(TokenKind.EXPORT, "expected 'export'")
        self._expect(TokenKind.COLON, "expected ':' after export")
        word_token = self._expect_definition_identifier("expected exported word name")
        if "." in word_token.lexeme:
            self._raise_error(
                "export declaration expects local word name",
                span=word_token.span,
            )
        return ExportDeclaration(span=self._span_from(start, word_token), word_name=word_token.lexeme)

    def _parse_qualified_module_name(self, message: str) -> QualifiedModuleName:
        token = self._expect(
            TokenKind.QUALIFIED_MODULE_NAME,
            message,
            code=_QUALIFIED_MODULE_NAME_ERROR_CODES.get(message),
        )
        parts = tuple(token.lexeme[1:].split("."))
        return QualifiedModuleName(span=token.span, parts=parts)

    def _parse_host_path(self) -> HostPathNode:
        token = self._current()
        if token.kind is TokenKind.QUALIFIED_MODULE_NAME:
            self._raise_error("host ABI paths are relative to @host", span=token.span)
        if token.kind is not TokenKind.IDENTIFIER:
            self._raise_error("expected host ABI path")

        self._advance()
        parts = tuple(token.lexeme.split("."))
        if not parts or any(part == "" for part in parts):
            self._raise_error("expected host ABI path", span=token.span)
        return HostPathNode(span=token.span, parts=parts)

    def _parse_host_require_declaration(self) -> HostRequireDeclaration:
        start = self._expect(TokenKind.REQUIRE, "unexpected token")
        path = self._parse_host_path()
        signature = self._parse_signature()
        signature_end_span = signature.span
        if self._index > 0:
            signature_end_token = self._tokens[self._index - 1]
            if signature_end_token.kind is TokenKind.RBRACE:
                signature_end_span = signature_end_token.span

        effect_token: Token
        effect: HostAbiEffect
        if self._check(TokenKind.PURE):
            effect_token = self._advance()
            effect = HostAbiEffect.PURE
        elif self._check(TokenKind.DIRTY):
            effect_token = self._advance()
            effect = HostAbiEffect.DIRTY
        else:
            self._raise_error("host requirement must declare an effect", span=signature_end_span)

        return HostRequireDeclaration(
            span=self._span_from(start, effect_token),
            path=path,
            signature=signature,
            effect=effect,
        )

    def _parse_host_opaque_declaration(self) -> HostOpaqueDeclaration:
        start = self._expect(TokenKind.OPAQUE, "unexpected token")
        path = self._parse_host_path()
        return HostOpaqueDeclaration(span=self._span_from(start, path), path=path)

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
        return ParameterNode(
            span=self._span_from(name_token, type_node),
            name=name_token.lexeme,
            type_node=type_node,
        )

    def _expect_definition_identifier(self, message: str) -> Token:
        token = self._current()
        if token.kind is TokenKind.DIRTY:
            self._raise_error(
                "cannot define reserved identifier: dirty",
                code="PARSER_RESERVED_IDENTIFIER",
                span=token.span,
            )
        return self._expect(
            TokenKind.IDENTIFIER,
            message,
            code=_DEFINITION_IDENTIFIER_ERROR_CODES.get(message),
        )

    def _parse_type(self) -> TypeNode | QuoteTypeNode:
        token = self._current()
        normalized_name: str
        if token.kind is TokenKind.IDENTIFIER:
            name_token = self._advance()
            normalized_name = name_token.lexeme
        elif token.kind is TokenKind.QUALIFIED_MODULE_NAME and token.lexeme.startswith("@host."):
            name_token = self._advance()
            # Transitional compatibility: keep downstream host opaque handling on host.* names.
            normalized_name = token.lexeme[1:]
        else:
            self._raise_error("malformed type")

        if normalized_name in {"Quote", "DirtyQuote"} and self._match(TokenKind.LT):
            if self._check(TokenKind.LBRACE):
                quote_type = self._parse_quote_type()
                end = self._expect(TokenKind.GT, "malformed type")
                quote_type.effect_kind = (
                    QuoteEffect.DIRTY
                    if normalized_name == "DirtyQuote"
                    else QuoteEffect.PURE
                )
                return TypeNode(
                    span=self._span_from(name_token, end),
                    name="Quote",
                    args=(quote_type,),
                )

        if self._match(TokenKind.LT):
            args, end = self._parse_type_arguments()
            return TypeNode(
                span=self._span_from(name_token, end),
                name=normalized_name,
                args=tuple(args),
            )

        return TypeNode(span=name_token.span, name=normalized_name)

    def _parse_type_arguments(self) -> tuple[list[TypeNode | QuoteTypeNode], Token]:
        args: list[TypeNode | QuoteTypeNode] = []
        if self._check(TokenKind.GT):
            self._raise_error("malformed type")
        while True:
            args.append(self._parse_type())
            if self._match(TokenKind.COMMA):
                continue
            end = self._expect(TokenKind.GT, "malformed type")
            return args, end

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
            self._expect(TokenKind.RBRACKET, "expected ']'")
            self._expect(TokenKind.COLON, "empty list requires explicit type annotation")
            type_node = self._parse_type()
            if type_node.name != "List":
                self._raise_error(
                    "empty list requires List<T> annotation",
                    span=type_node.span,
                )
            return TypedEmptyListNode(
                span=self._span_from(start, type_node),
                type_node=type_node,
            )

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
            self._raise_error(
                "map.empty requires Map<K,V> annotation",
                span=type_node.span,
            )
        return TypedEmptyMapNode(span=self._span_from(start, type_node), type_node=type_node)

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

        end = self._expect(TokenKind.END, "missing 'end'")
        return CaseNode(span=self._span_from(start, end), branches=tuple(branches))

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
        boundary_span = self._current().span
        boundary_start_span = SourceSpan(
            source=boundary_span.source,
            start=boundary_span.start,
            end=boundary_span.start,
        )
        return CaseBranchNode(
            span=self._span_from(pattern, boundary_start_span),
            pattern=pattern,
            body=body,
            guard=guard,
        )

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
            self._raise_error(
                "unexpected token",
                code="PARSER_INVALID_PATTERN",
                suggestion="use _, literal, MissingKey/OutOfBounds, Ok(name), or Err(name)",
            )

        self._raise_error(
            "unexpected token",
            code="PARSER_INVALID_PATTERN",
            suggestion="use _, literal, MissingKey/OutOfBounds, Ok(name), or Err(name)",
        )

    def _parse_constructor_pattern(self, token: Token, index: int) -> tuple[PatternNode, int]:
        inner_index = index + 2
        if inner_index >= len(self._tokens):
            self._raise_error("unexpected end of input", span=self._current().span)

        binding_token = self._tokens[inner_index]
        if binding_token.kind is not TokenKind.IDENTIFIER:
            self._raise_error(
                "unexpected token",
                code="PARSER_INVALID_PATTERN",
                suggestion="use Ok(name) or Err(name) constructor patterns",
                span=binding_token.span,
            )

        close_index = inner_index + 1
        if close_index >= len(self._tokens):
            self._raise_error("unexpected end of input", span=self._current().span)
        close_token = self._tokens[close_index]
        if close_token.kind is TokenKind.LPAREN:
            self._raise_error(
                "unexpected token",
                code="PARSER_INVALID_PATTERN",
                suggestion="constructor patterns do not support nested constructors",
                span=binding_token.span,
            )
        if close_token.kind is not TokenKind.RPAREN:
            self._raise_error(
                "unexpected token",
                code="PARSER_INVALID_PATTERN",
                suggestion="close constructor patterns with ')'",
                span=close_token.span,
            )

        kind = PatternKind.OK if token.lexeme == "Ok" else PatternKind.ERR
        value = None
        binding = binding_token.lexeme
        if kind is PatternKind.ERR and binding_token.lexeme in _ERR_VARIANT_PATTERN_NAMES:
            value = binding_token.lexeme
            binding = None

        return (
            PatternNode(
                span=self._span_from(token, close_token),
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
                self._raise_error(
                    message,
                    code="PARSER_DUPLICATE_LOCAL_NAME",
                    span=param.span,
                )
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

    def _expect(
        self,
        kind: TokenKind,
        message: str,
        *,
        code: str | None = None,
        suggestion: str | None = None,
    ) -> Token:
        token = self._current()
        if token.kind is not kind:
            self._raise_error(message, code=code, span=token.span, suggestion=suggestion)
        self._advance()
        return token

    def _current(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        if self._index < len(self._tokens) - 1:
            self._index += 1
        return token

    def _raise_error(
        self,
        message: str,
        *,
        code: str | None = None,
        span: SourceSpan | None = None,
        suggestion: str | None = None,
    ) -> None:
        resolved_code = code
        resolved_suggestion = suggestion
        if resolved_code is None:
            mapped_details = _PARSER_ERROR_DETAILS.get(message)
            if mapped_details is not None:
                resolved_code, mapped_suggestion = mapped_details
                if resolved_suggestion is None:
                    resolved_suggestion = mapped_suggestion
            else:
                resolved_code = "PARSER_ERROR"
        resolved_span = span if span is not None else self._current().span
        raise ParseError(
            message=message,
            line=resolved_span.line,
            column=resolved_span.column,
            code=resolved_code,
            span=resolved_span,
            suggestion=resolved_suggestion,
        )

    def _validate_user_word_name(self, token: Token) -> None:
        lexeme = token.lexeme
        if lexeme in _RESERVED_WORD_NAMES:
            self._raise_error(
                message=f"cannot define reserved word: {lexeme}",
                code="PARSER_RESERVED_WORD",
                span=token.span,
            )
        for prefix in _RESERVED_WORD_PREFIXES:
            if lexeme.startswith(prefix):
                self._raise_error(
                    message=f"cannot define reserved namespace word: {lexeme}",
                    code="PARSER_RESERVED_NAMESPACE_WORD",
                    span=token.span,
                )
        if "." in lexeme:
            self._raise_error(
                message=f"cannot define qualified word name: {lexeme}",
                code="PARSER_QUALIFIED_WORD_DEFINITION",
                span=token.span,
            )
