from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from nicole.tokens import SourceSpan

__all__ = [
    "ASTNode",
    "AtomNode",
    "BlockNode",
    "CaseBranchNode",
    "CaseNode",
    "IdentifierNode",
    "IfNode",
    "LiteralKind",
    "LiteralNode",
    "ListLiteralNode",
    "OperatorNode",
    "ParameterNode",
    "PatternKind",
    "PatternNode",
    "ProgramNode",
    "QuoteNode",
    "QuoteTypeNode",
    "ResolutionInfo",
    "SignatureNode",
    "TypedEmptyListNode",
    "TypedEmptyMapNode",
    "TypeNode",
    "Visibility",
    "WordDefNode",
]


class Visibility(Enum):
    PRIVATE = auto()
    PUB = auto()
    EXPORT = auto()


class LiteralKind(Enum):
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    BOOL = auto()


class PatternKind(Enum):
    LITERAL = auto()
    WILDCARD = auto()
    OK = auto()
    ERR = auto()
    NAME = auto()


@dataclass(slots=True)
class ResolutionInfo:
    resolved_symbol: object | None = None
    owner_scope: str | None = None
    qualified_name: str | None = None
    visibility: Visibility | None = None
    signature_reference: SignatureNode | None = None


@dataclass(slots=True)
class ASTNode:
    span: SourceSpan
    resolution: ResolutionInfo = field(
        default_factory=ResolutionInfo,
        init=False,
        repr=False,
        compare=False,
    )


@dataclass(slots=True)
class AtomNode(ASTNode):
    pass


@dataclass(slots=True)
class ProgramNode(ASTNode):
    words: tuple[WordDefNode, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class WordDefNode(ASTNode):
    name: str
    signature: SignatureNode
    body: BlockNode
    visibility: Visibility = Visibility.PRIVATE
    nested_words: tuple[WordDefNode, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class SignatureNode(ASTNode):
    inputs: tuple[ParameterNode, ...] = field(default_factory=tuple)
    outputs: tuple[ParameterNode, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class ParameterNode(ASTNode):
    name: str
    type_node: TypeNode


@dataclass(slots=True)
class TypeNode(ASTNode):
    name: str
    args: tuple[TypeNode | QuoteTypeNode, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class QuoteTypeNode(ASTNode):
    captures: tuple[ParameterNode, ...] = field(default_factory=tuple)
    inputs: tuple[ParameterNode, ...] = field(default_factory=tuple)
    outputs: tuple[ParameterNode, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class BlockNode(ASTNode):
    items: tuple[AtomNode, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class IdentifierNode(AtomNode):
    name: str


@dataclass(slots=True)
class OperatorNode(AtomNode):
    operator: str


@dataclass(slots=True)
class LiteralNode(AtomNode):
    kind: LiteralKind
    value: object
    raw: str


@dataclass(slots=True)
class ListLiteralNode(AtomNode):
    elements: tuple[AtomNode, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class TypedEmptyListNode(AtomNode):
    type_node: TypeNode


@dataclass(slots=True)
class TypedEmptyMapNode(AtomNode):
    type_node: TypeNode


@dataclass(slots=True)
class IfNode(AtomNode):
    then_block: BlockNode
    else_block: BlockNode


@dataclass(slots=True)
class CaseBranchNode(ASTNode):
    pattern: PatternNode
    body: BlockNode


@dataclass(slots=True)
class CaseNode(AtomNode):
    branches: tuple[CaseBranchNode, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class PatternNode(ASTNode):
    kind: PatternKind = PatternKind.WILDCARD
    value: object | None = None
    binding: str | None = None


@dataclass(slots=True)
class QuoteNode(AtomNode):
    body: BlockNode
    captures: tuple[ParameterNode, ...] = field(default_factory=tuple)
    inputs: tuple[ParameterNode, ...] = field(default_factory=tuple)
    outputs: tuple[ParameterNode, ...] = field(default_factory=tuple)
