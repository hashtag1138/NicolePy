from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import (
    BlockNode,
    CaseBranchNode,
    CaseNode,
    IdentifierNode,
    IfNode,
    ListLiteralNode,
    LiteralNode,
    OperatorNode,
    PatternNode,
    ProgramNode,
    QuoteNode,
    ResolutionInfo,
    WordDefNode,
)
from .host_abi import BindingAvailability, HostContract
from .symbols import SymbolSource, SymbolTable, WordSymbol

__all__ = ["ResolutionError", "Resolver", "resolve"]


@dataclass(slots=True)
class ResolutionError(Exception):
    message: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.message} at {self.line}:{self.column}"


class Resolver:
    def __init__(self, symbols: SymbolTable, host_contract: HostContract | None = None) -> None:
        self._symbols = symbols
        self._host_contract = host_contract

    def resolve(self, program: ProgramNode) -> ProgramNode:
        for word in program.words:
            self._resolve_word(word, lexical_owner=None)
        return program

    def _resolve_word(self, word: WordDefNode, lexical_owner: str | None) -> None:
        symbol = self._find_definition_symbol(word, lexical_owner)
        if symbol is None:
            self._raise_error("unresolved word definition", word.span.line, word.span.column)

        current_scope = symbol.qualified_name
        current_locals = {parameter.name for parameter in word.signature.inputs}
        self._resolve_block(word.body, current_scope=current_scope, local_names=current_locals)

        for nested_word in word.nested_words:
            self._resolve_word(nested_word, lexical_owner=current_scope)

    def _resolve_block(self, block: BlockNode, *, current_scope: str | None, local_names: set[str]) -> None:
        for item in block.items:
            if isinstance(item, IdentifierNode):
                self._resolve_identifier(item, current_scope=current_scope, local_names=local_names)
            elif isinstance(item, OperatorNode):
                continue
            elif isinstance(item, LiteralNode):
                continue
            elif isinstance(item, ListLiteralNode):
                self._resolve_list_literal(item, current_scope=current_scope, local_names=local_names)
            elif isinstance(item, IfNode):
                self._resolve_block(item.then_block, current_scope=current_scope, local_names=local_names)
                self._resolve_block(item.else_block, current_scope=current_scope, local_names=local_names)
            elif isinstance(item, CaseNode):
                self._resolve_case(item, current_scope=current_scope, local_names=local_names)
            elif isinstance(item, QuoteNode):
                self._resolve_quote(item, current_scope=current_scope, local_names=local_names)
            elif isinstance(item, PatternNode):
                continue

    def _resolve_case(self, case: CaseNode, *, current_scope: str | None, local_names: set[str]) -> None:
        for branch in case.branches:
            self._resolve_case_branch(branch, current_scope=current_scope, local_names=local_names)

    def _resolve_case_branch(
        self,
        branch: CaseBranchNode,
        *,
        current_scope: str | None,
        local_names: set[str],
    ) -> None:
        branch_locals = set(local_names)
        if branch.pattern.binding is not None:
            branch_locals.add(branch.pattern.binding)
        if branch.guard is not None:
            self._resolve_block(branch.guard, current_scope=current_scope, local_names=branch_locals)
        self._resolve_block(branch.body, current_scope=current_scope, local_names=branch_locals)

    def _resolve_quote(
        self,
        quote: QuoteNode,
        *,
        current_scope: str | None,
        local_names: set[str],
    ) -> None:
        quote_locals = {parameter.name for parameter in quote.captures}
        quote_locals.update(parameter.name for parameter in quote.inputs)
        self._resolve_block(quote.body, current_scope=current_scope, local_names=quote_locals)

    def _resolve_list_literal(
        self,
        list_literal: ListLiteralNode,
        *,
        current_scope: str | None,
        local_names: set[str],
    ) -> None:
        for element in list_literal.elements:
            if isinstance(element, IdentifierNode):
                self._resolve_identifier(element, current_scope=current_scope, local_names=local_names)
            elif isinstance(element, OperatorNode):
                continue
            elif isinstance(element, LiteralNode):
                continue
            elif isinstance(element, ListLiteralNode):
                self._resolve_list_literal(element, current_scope=current_scope, local_names=local_names)
            elif isinstance(element, IfNode):
                self._resolve_block(element.then_block, current_scope=current_scope, local_names=local_names)
                self._resolve_block(element.else_block, current_scope=current_scope, local_names=local_names)
            elif isinstance(element, CaseNode):
                self._resolve_case(element, current_scope=current_scope, local_names=local_names)
            elif isinstance(element, QuoteNode):
                self._resolve_quote(element, current_scope=current_scope, local_names=local_names)

    def _resolve_identifier(
        self,
        node: IdentifierNode,
        *,
        current_scope: str | None,
        local_names: set[str],
    ) -> None:
        if node.name in local_names:
            self._annotate_local(node, current_scope=current_scope, name=node.name)
            return

        if node.name.startswith("host."):
            self._annotate_host(node)
            return

        symbol = self._lookup_symbol(node.name, current_scope=current_scope)
        if symbol is None:
            self._raise_error("unresolved name", node.span.line, node.span.column)

        self._annotate_symbol_node(
            node,
            symbol,
            owner_scope=symbol.owner or "module",
        )

    def _lookup_symbol(self, name: str, *, current_scope: str | None) -> WordSymbol | None:
        by_name = self._symbols.words.get(name, [])
        if not by_name:
            return None

        for scope in _scope_chain(current_scope):
            for symbol in by_name:
                if symbol.owner == scope:
                    return symbol
        for symbol in by_name:
            if symbol.source is SymbolSource.BUILTIN:
                return symbol
        return None

    def _find_definition_symbol(
        self,
        word: WordDefNode,
        lexical_owner: str | None,
    ) -> WordSymbol | None:
        for symbol in self._symbols.words.get(word.name, []):
            if symbol.owner == lexical_owner:
                return symbol
        return None

    def _annotate_symbol_node(self, node, symbol: WordSymbol, *, owner_scope: str) -> None:
        node.resolution = ResolutionInfo(
            resolved_symbol=symbol,
            owner_scope=owner_scope,
            qualified_name=symbol.qualified_name,
            visibility=symbol.visibility,
            signature_reference=symbol.signature,
            declared_dirty=symbol.declared_dirty,
        )

    def _annotate_local(self, node: IdentifierNode, *, current_scope: str | None, name: str) -> None:
        node.resolution = ResolutionInfo(
            resolved_symbol=None,
            owner_scope=current_scope or "module",
            qualified_name=f"local:{name}",
            visibility=None,
            signature_reference=None,
        )

    def _annotate_host(self, node: IdentifierNode) -> None:
        if self._host_contract is None:
            self._raise_error("host contract required for host.* reference", node.span.line, node.span.column)
        host_word = self._host_contract.words.get(node.name)
        if host_word is None:
            self._raise_error("unknown host word", node.span.line, node.span.column)
        if host_word.availability is BindingAvailability.OPTIONAL:
            self._raise_error(
                "optional host word cannot be called directly in v1",
                node.span.line,
                node.span.column,
            )
        node.resolution = ResolutionInfo(
            resolved_symbol=host_word,
            owner_scope="host",
            qualified_name=node.name,
            visibility=None,
            signature_reference=host_word.signature,
            host_effect=host_word.effect,
        )

    def _raise_error(self, message: str, line: int, column: int) -> None:
        raise ResolutionError(message=message, line=line, column=column)


def resolve(program: ProgramNode, symbols: SymbolTable, host_contract: HostContract | None = None) -> ProgramNode:
    return Resolver(symbols, host_contract=host_contract).resolve(program)


def _scope_chain(current_scope: str | None) -> list[str | None]:
    if current_scope is None:
        return [None]

    parts = current_scope.split(".")
    chain: list[str | None] = [".".join(parts[:index]) for index in range(len(parts), 0, -1)]
    chain.append(None)
    return chain
