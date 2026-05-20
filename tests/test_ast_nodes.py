from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.ast_nodes import (
    ASTNode,
    AtomNode,
    BlockNode,
    CaseBranchNode,
    CaseNode,
    IdentifierNode,
    IfNode,
    LiteralKind,
    LiteralNode,
    ListLiteralNode,
    OperatorNode,
    ParameterNode,
    PatternNode,
    PatternKind,
    ProgramNode,
    QuoteEffect,
    QuoteNode,
    QuoteTypeNode,
    SignatureNode,
    TypedEmptyListNode,
    TypedEmptyMapNode,
    TypeNode,
    Visibility,
    WordDefNode,
)
from nicole.tokens import SourceSpan


def make_span(line: int = 1, column: int = 1, offset: int = 0) -> SourceSpan:
    return SourceSpan(line=line, column=column, offset=offset)


def test_source_span_creation():
    span = make_span(2, 5, 12)
    assert span.line == 2
    assert span.column == 5
    assert span.offset == 12


def test_identifier_node_creation():
    node = IdentifierNode(name="add", span=make_span())
    assert node.name == "add"
    assert node.span == make_span()


def test_block_node_with_identifier_and_operator():
    node = BlockNode(
        items=(
            IdentifierNode(name="a", span=make_span(1, 1, 0)),
            OperatorNode(operator="+", span=make_span(1, 3, 2)),
        ),
        span=make_span(),
    )
    assert len(node.items) == 2
    assert node.items[0].name == "a"
    assert node.items[1].operator == "+"


def test_word_def_node_minimal():
    node = WordDefNode(
        name="add",
        visibility=Visibility.PRIVATE,
        signature=SignatureNode(span=make_span(), inputs=(), outputs=()),
        body=BlockNode(span=make_span(), items=()),
        nested_words=(),
        span=make_span(),
    )
    assert node.name == "add"
    assert node.visibility is Visibility.PRIVATE
    assert node.is_dirty_annotation is False


def test_word_def_node_can_store_dirty_annotation_metadata():
    node = WordDefNode(
        name="add",
        visibility=Visibility.PRIVATE,
        signature=SignatureNode(span=make_span(), inputs=(), outputs=()),
        body=BlockNode(span=make_span(), items=()),
        is_dirty_annotation=True,
        nested_words=(),
        span=make_span(),
    )

    assert node.is_dirty_annotation is True


def test_if_node_has_no_condition_field():
    field_names = {field.name for field in IfNode.__dataclass_fields__.values()}
    assert "condition" not in field_names


def test_case_node_has_no_scrutinee_field():
    field_names = {field.name for field in CaseNode.__dataclass_fields__.values()}
    assert "scrutinee" not in field_names


@pytest.mark.parametrize(
    "cls, kwargs",
    [
        (ProgramNode, {"words": (), "span": make_span()}),
        (
            SignatureNode,
            {"inputs": (), "outputs": (), "span": make_span()},
        ),
        (
            ParameterNode,
            {
                "name": "x",
                "type_node": TypeNode(name="Int", span=make_span()),
                "span": make_span(),
            },
        ),
        (
            TypeNode,
            {"name": "Int", "args": (), "span": make_span()},
        ),
        (
            QuoteTypeNode,
            {"captures": (), "inputs": (), "outputs": (), "span": make_span()},
        ),
        (BlockNode, {"items": (), "span": make_span()}),
        (IdentifierNode, {"name": "x", "span": make_span()}),
        (OperatorNode, {"operator": "+", "span": make_span()}),
        (
            LiteralNode,
            {
                "kind": LiteralKind.INT,
                "value": 1,
                "raw": "1",
                "span": make_span(),
            },
        ),
        (ListLiteralNode, {"elements": (), "span": make_span()}),
        (
            TypedEmptyListNode,
            {"type_node": TypeNode(name="List", args=(TypeNode(name="Int", span=make_span()),), span=make_span()), "span": make_span()},
        ),
        (
            TypedEmptyMapNode,
            {
                "type_node": TypeNode(
                    name="Map",
                    args=(
                        TypeNode(name="String", span=make_span()),
                        TypeNode(name="Int", span=make_span()),
                    ),
                    span=make_span(),
                ),
                "span": make_span(),
            },
        ),
        (
            IfNode,
            {
                "then_block": BlockNode(span=make_span()),
                "else_block": BlockNode(span=make_span()),
                "span": make_span(),
            },
        ),
        (
            PatternNode,
            {"kind": PatternKind.WILDCARD, "value": None, "binding": None, "span": make_span()},
        ),
        (
            CaseBranchNode,
            {
                "pattern": PatternNode(
                    kind=PatternKind.WILDCARD,
                    value=None,
                    binding=None,
                    span=make_span(),
                ),
                "body": BlockNode(span=make_span()),
                "span": make_span(),
            },
        ),
        (
            CaseNode,
            {"branches": (), "span": make_span()},
        ),
        (
            QuoteNode,
            {
                "captures": (),
                "inputs": (),
                "outputs": (),
                "body": BlockNode(span=make_span()),
                "span": make_span(),
            },
        ),
    ],
)
def test_important_nodes_carry_span(cls, kwargs):
    node = cls(**kwargs)
    assert isinstance(node.span, SourceSpan)


def test_quote_type_node_defaults_to_pure_effect_kind():
    node = QuoteTypeNode(span=make_span(), captures=(), inputs=(), outputs=())
    assert node.effect_kind is QuoteEffect.PURE


def test_quote_type_node_can_store_dirty_effect_kind():
    node = QuoteTypeNode(
        span=make_span(),
        effect_kind=QuoteEffect.DIRTY,
        captures=(),
        inputs=(),
        outputs=(),
    )
    assert node.effect_kind is QuoteEffect.DIRTY
