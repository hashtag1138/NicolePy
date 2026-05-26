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
    ExportDeclaration,
    HostAbiEffect,
    HostOpaqueDeclaration,
    HostPathNode,
    HostRequireDeclaration,
    IdentifierNode,
    ImportDeclaration,
    ImportAliasKind,
    IncludeDeclaration,
    IfNode,
    LiteralKind,
    LiteralNode,
    ListLiteralNode,
    ModuleDeclaration,
    OperatorNode,
    ParameterNode,
    PatternNode,
    PatternKind,
    ProgramNode,
    QualifiedModuleName,
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


def test_qualified_module_name_node_creation():
    node = QualifiedModuleName(parts=("app", "run"), span=make_span())

    assert node.parts == ("app", "run")


def test_module_import_include_export_nodes_creation():
    qualified = QualifiedModuleName(parts=("app",), span=make_span())
    module_node = ModuleDeclaration(name=qualified, span=make_span())
    import_node = ImportDeclaration(target=qualified, alias="a", span=make_span())
    include_node = IncludeDeclaration(path="feature.nic", span=make_span())
    export_node = ExportDeclaration(word_name="run", span=make_span())

    assert module_node.name.parts == ("app",)
    assert module_node.is_host_module is False
    assert import_node.target.parts == ("app",)
    assert import_node.alias == "a"
    assert import_node.is_grouped is False
    assert import_node.grouped_members == ()
    assert import_node.alias_kind is ImportAliasKind.NONE
    assert include_node.path == "feature.nic"
    assert export_node.word_name == "run"


def test_host_abi_effect_enum_values():
    assert HostAbiEffect.PURE.value == "pure"
    assert HostAbiEffect.DIRTY.value == "dirty"


def test_import_alias_kind_enum_values():
    assert ImportAliasKind.NONE.value == "none"
    assert ImportAliasKind.SIMPLE.value == "simple"
    assert ImportAliasKind.PREFIX.value == "prefix"
    assert ImportAliasKind.STAR.value == "star"


def test_module_declaration_host_flag_is_additive_and_compatible():
    qualified = QualifiedModuleName(parts=("app",), span=make_span())

    module_default = ModuleDeclaration(name=qualified, span=make_span())
    assert module_default.is_host_module is False

    module_host = ModuleDeclaration(name=qualified, span=make_span(), is_host_module=True)
    assert module_host.is_host_module is True


def test_host_path_node_stores_parts_and_span():
    span = make_span(2, 3, 8)
    path = HostPathNode(parts=("console", "log"), span=span)

    assert path.parts == ("console", "log")
    assert path.span == span


def test_host_require_declaration_stores_path_signature_effect_and_span():
    span = make_span(4, 1, 12)
    path = HostPathNode(parts=("console", "log"), span=span)
    signature = SignatureNode(span=make_span(), inputs=(), outputs=())
    require_node = HostRequireDeclaration(
        path=path,
        signature=signature,
        effect=HostAbiEffect.DIRTY,
        span=span,
    )

    assert require_node.path is path
    assert require_node.signature is signature
    assert require_node.effect is HostAbiEffect.DIRTY
    assert require_node.span == span


def test_host_opaque_declaration_stores_path_and_span():
    span = make_span(5, 1, 20)
    path = HostPathNode(parts=("io", "FileHandle"), span=span)
    opaque_node = HostOpaqueDeclaration(path=path, span=span)

    assert opaque_node.path is path
    assert opaque_node.span == span


def test_import_declaration_grouped_prefix_shape():
    target = QualifiedModuleName(parts=("host", "io"), span=make_span())
    node = ImportDeclaration(
        target=target,
        alias="io",
        is_grouped=True,
        grouped_members=("open-file", "close-file", "FileHandle"),
        alias_kind=ImportAliasKind.PREFIX,
        span=make_span(),
    )

    assert node.target is target
    assert node.alias == "io"
    assert node.is_grouped is True
    assert node.grouped_members == ("open-file", "close-file", "FileHandle")
    assert node.alias_kind is ImportAliasKind.PREFIX


def test_import_declaration_grouped_as_star_shape():
    target = QualifiedModuleName(parts=("host", "console"), span=make_span())
    node = ImportDeclaration(
        target=target,
        alias=None,
        is_grouped=True,
        grouped_members=("log", "read-line"),
        alias_kind=ImportAliasKind.STAR,
        span=make_span(),
    )

    assert node.target is target
    assert node.alias is None
    assert node.is_grouped is True
    assert node.grouped_members == ("log", "read-line")
    assert node.alias_kind is ImportAliasKind.STAR


def test_if_node_has_no_condition_field():
    field_names = {field.name for field in IfNode.__dataclass_fields__.values()}
    assert "condition" not in field_names


def test_case_node_has_no_scrutinee_field():
    field_names = {field.name for field in CaseNode.__dataclass_fields__.values()}
    assert "scrutinee" not in field_names


def test_case_branch_node_has_optional_guard_field():
    field_names = {field.name for field in CaseBranchNode.__dataclass_fields__.values()}
    assert "guard" in field_names

    branch = CaseBranchNode(
        pattern=PatternNode(kind=PatternKind.WILDCARD, value=None, binding=None, span=make_span()),
        body=BlockNode(span=make_span(), items=()),
        span=make_span(),
    )
    assert branch.guard is None


@pytest.mark.parametrize(
    "cls, kwargs",
    [
        (ProgramNode, {"words": (), "span": make_span()}),
        (
            SignatureNode,
            {"inputs": (), "outputs": (), "span": make_span()},
        ),
        (
            QualifiedModuleName,
            {"parts": ("app",), "span": make_span()},
        ),
        (
            ModuleDeclaration,
            {
                "name": QualifiedModuleName(parts=("app",), span=make_span()),
                "span": make_span(),
            },
        ),
        (
            ImportDeclaration,
            {
                "target": QualifiedModuleName(parts=("app", "run"), span=make_span()),
                "alias": "runner",
                "span": make_span(),
            },
        ),
        (
            IncludeDeclaration,
            {"path": "core.nic", "span": make_span()},
        ),
        (
            ExportDeclaration,
            {"word_name": "run", "span": make_span()},
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
