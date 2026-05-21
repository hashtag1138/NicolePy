from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import ParameterNode, QuoteTypeNode, SignatureNode, TypeNode, Visibility
from .symbols import SymbolSource, SymbolTable, WordSymbol
from .tokens import SourceSpan

__all__ = [
    "StandardSymbolError",
    "load_standard_symbols",
    "with_standard_symbols",
]

_SYNTHETIC_SPAN = SourceSpan(line=0, column=0, offset=0)
_BUILTIN_OWNER = "std"


@dataclass(slots=True)
class StandardSymbolError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def load_standard_symbols() -> list[WordSymbol]:
    return [
        _builtin(
            "result.is-ok",
            inputs=(_param("r", _result_of(_named_type("T"), _named_type("E"))),),
            outputs=(_param("b", _named_type("Bool")),),
        ),
        _builtin(
            "result.is-err",
            inputs=(_param("r", _result_of(_named_type("T"), _named_type("E"))),),
            outputs=(_param("b", _named_type("Bool")),),
        ),
        _builtin(
            "result.unwrap-or",
            inputs=(
                _param("r", _result_of(_named_type("T"), _named_type("E"))),
                _param("fallback", _named_type("T")),
            ),
            outputs=(_param("value", _named_type("T")),),
        ),
        _builtin(
            "list.len",
            inputs=(_param("xs", _list_of("T")),),
            outputs=(_param("n", _named_type("Int")),),
        ),
        _builtin(
            "list.get",
            inputs=(
                _param("xs", _list_of("T")),
                _param("index", _named_type("Int")),
            ),
            outputs=(_param("r", _result_of(_named_type("T"), _named_type("ListError"))),),
        ),
        _builtin(
            "list.set",
            inputs=(
                _param("xs", _list_of("T")),
                _param("index", _named_type("Int")),
                _param("value", _named_type("T")),
            ),
            outputs=(_param("r", _result_of(_list_of("T"), _named_type("ListError"))),),
        ),
        _builtin(
            "list.concat",
            inputs=(
                _param("xs", _list_of("T")),
                _param("ys", _list_of("T")),
            ),
            outputs=(_param("zs", _list_of("T")),),
        ),
        _builtin(
            "list.map",
            inputs=(
                _param("xs", _list_of("T")),
                _param("q", _quote_type((), (("x", "T"),), (("y", "U"),))),
            ),
            outputs=(_param("ys", _list_of("U")),),
            quote_callable_only=True,
        ),
        _builtin(
            "list.filter",
            inputs=(
                _param("xs", _list_of("T")),
                _param("q", _quote_type((), (("x", "T"),), (("keep", "Bool"),))),
            ),
            outputs=(_param("ys", _list_of("T")),),
            quote_callable_only=True,
        ),
        _builtin(
            "list.fold",
            inputs=(
                _param("xs", _list_of("T")),
                _param("init", _named_type("Acc")),
                _param("q", _quote_type((), (("acc", "Acc"), ("x", "T")), (("out", "Acc"),))),
            ),
            outputs=(_param("out", _named_type("Acc")),),
            quote_callable_only=True,
        ),
        _builtin(
            "list.reduce",
            inputs=(
                _param("xs", _list_of("T")),
                _param("q", _quote_type((), (("a", "T"), ("b", "T")), (("c", "T"),))),
            ),
            outputs=(_param("out", _named_type("T")),),
            quote_callable_only=True,
        ),
        _builtin(
            "map.get",
            inputs=(
                _param("m", _map_of("K", "V")),
                _param("k", _named_type("K")),
            ),
            outputs=(_param("r", _result_of(_named_type("V"), _named_type("MapError"))),),
        ),
        _builtin(
            "map.contains",
            inputs=(
                _param("m", _map_of("K", "V")),
                _param("k", _named_type("K")),
            ),
            outputs=(_param("ok", _named_type("Bool")),),
        ),
        _builtin(
            "map.set",
            inputs=(
                _param("m", _map_of("K", "V")),
                _param("k", _named_type("K")),
                _param("v", _named_type("V")),
            ),
            outputs=(_param("m2", _map_of("K", "V")),),
        ),
        _builtin(
            "map.remove",
            inputs=(
                _param("m", _map_of("K", "V")),
                _param("k", _named_type("K")),
            ),
            outputs=(_param("r", _result_of(_map_of("K", "V"), _named_type("MapError"))),),
        ),
        _builtin(
            "map.len",
            inputs=(_param("m", _map_of("K", "V")),),
            outputs=(_param("n", _named_type("Int")),),
        ),
    ]


def with_standard_symbols(table: SymbolTable) -> SymbolTable:
    enriched = SymbolTable(words={name: list(symbols) for name, symbols in table.words.items()})
    for builtin in load_standard_symbols():
        existing = enriched.words.get(builtin.name, [])
        if any(symbol.source is SymbolSource.USER for symbol in existing):
            raise StandardSymbolError(f"cannot redefine standard builtin: {builtin.name}")
        if any(
            symbol.source is SymbolSource.BUILTIN and symbol.qualified_name == builtin.qualified_name
            for symbol in existing
        ):
            continue
        enriched.add(builtin)
    return enriched


def _builtin(
    name: str,
    *,
    inputs: tuple[ParameterNode, ...],
    outputs: tuple[ParameterNode, ...],
    quote_callable_only: bool = False,
) -> WordSymbol:
    return WordSymbol(
        name=name,
        signature=SignatureNode(span=_SYNTHETIC_SPAN, inputs=inputs, outputs=outputs),
        visibility=Visibility.PUB,
        span=_SYNTHETIC_SPAN,
        owner=_BUILTIN_OWNER,
        source=SymbolSource.BUILTIN,
        quote_callable_only=quote_callable_only,
    )


def _param(name: str, type_node: TypeNode) -> ParameterNode:
    return ParameterNode(span=_SYNTHETIC_SPAN, name=name, type_node=type_node)


def _named_type(name: str) -> TypeNode:
    return TypeNode(span=_SYNTHETIC_SPAN, name=name)


def _list_of(item_name: str) -> TypeNode:
    return TypeNode(span=_SYNTHETIC_SPAN, name="List", args=(_named_type(item_name),))


def _map_of(key_name: str, value_name: str) -> TypeNode:
    return TypeNode(
        span=_SYNTHETIC_SPAN,
        name="Map",
        args=(_named_type(key_name), _named_type(value_name)),
    )


def _result_of(value_type: TypeNode, error_type: TypeNode) -> TypeNode:
    return TypeNode(span=_SYNTHETIC_SPAN, name="Result", args=(value_type, error_type))


def _quote_type(
    captures: tuple[tuple[str, str], ...],
    inputs: tuple[tuple[str, str], ...],
    outputs: tuple[tuple[str, str], ...],
) -> TypeNode:
    return TypeNode(
        span=_SYNTHETIC_SPAN,
        name="Quote",
        args=(
            QuoteTypeNode(
                span=_SYNTHETIC_SPAN,
                captures=tuple(_param(name, _named_type(type_name)) for name, type_name in captures),
                inputs=tuple(_param(name, _named_type(type_name)) for name, type_name in inputs),
                outputs=tuple(_param(name, _named_type(type_name)) for name, type_name in outputs),
            ),
        ),
    )
