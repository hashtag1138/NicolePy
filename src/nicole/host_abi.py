from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from types import MappingProxyType

from .ast_nodes import QuoteTypeNode, SignatureNode, TypeNode, Visibility
from .symbols import SymbolTable

_ABI_SCALAR_TYPES_V1 = {
    "Int",
    "Float",
    "String",
    "Bool",
    "Unit",
    "ListError",
    "MapError",
}


@dataclass(slots=True)
class HostABIError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


class BindingAvailability(Enum):
    REQUIRED = auto()
    OPTIONAL = auto()


class HostEffect(Enum):
    PURE = auto()
    DIRTY = auto()


@dataclass(slots=True)
class HostWord:
    name: str
    signature: SignatureNode
    effect: HostEffect
    availability: BindingAvailability = BindingAvailability.REQUIRED

    def __post_init__(self) -> None:
        if not isinstance(self.effect, HostEffect):
            raise HostABIError("host word effect must be HostEffect.PURE or HostEffect.DIRTY")


@dataclass(slots=True)
class ExportWord:
    export_name: str
    internal_name: str
    signature: SignatureNode


@dataclass(frozen=True, slots=True)
class HostContract:
    words: Mapping[str, HostWord]


def empty_host_contract() -> HostContract:
    return HostContract(words=MappingProxyType({}))


def host_contract_from_words(words: Iterable[HostWord]) -> HostContract:
    entries: dict[str, HostWord] = {}
    for word in words:
        if not word.name.startswith("host."):
            raise HostABIError(f"host word name must start with 'host.': {word.name}")
        if word.name in entries:
            raise HostABIError(f"duplicate host word: {word.name}")
        _validate_signature_types(word.signature, forbid_quote=True)
        entries[word.name] = word
    return HostContract(words=MappingProxyType(entries))


@dataclass(frozen=True, slots=True)
class ExportContract:
    words: Mapping[str, ExportWord]


def empty_export_contract() -> ExportContract:
    return ExportContract(words=MappingProxyType({}))


def export_contract_from_words(words: Iterable[ExportWord]) -> ExportContract:
    entries: dict[str, ExportWord] = {}
    for word in words:
        if word.export_name in entries:
            raise HostABIError(f"duplicate export word: {word.export_name}")
        entries[word.export_name] = word
    return ExportContract(words=MappingProxyType(entries))


def collect_exports(symbols: SymbolTable) -> ExportContract:
    exports: list[ExportWord] = []
    for symbols_for_name in symbols.words.values():
        for symbol in symbols_for_name:
            if symbol.visibility is not Visibility.EXPORT:
                continue
            if symbol.module is None:
                raise HostABIError(f"export symbol missing module ownership: {symbol.name}")
            if symbol.owner is not None:
                raise HostABIError(
                    f"export target must be module-level word: @{symbol.module}.{symbol.qualified_name}"
                )
            _validate_signature_types(symbol.signature, forbid_quote=True)
            canonical_name = f"@{symbol.module}.{symbol.name}"
            internal_name = f"@{symbol.module}.{symbol.qualified_name}"
            exports.append(
                ExportWord(
                    export_name=canonical_name,
                    internal_name=internal_name,
                    signature=symbol.signature,
                )
            )
    return export_contract_from_words(exports)


def validate_type_v1(
    type_node: TypeNode,
    *,
    forbid_quote: bool,
) -> None:
    if type_node.name in {"Quote", "DirtyQuote"}:
        if forbid_quote:
            raise HostABIError("Quote is forbidden across ABI in v1 (including DirtyQuote)")
        if len(type_node.args) != 1:
            return
        quote_signature = type_node.args[0]
        if not isinstance(quote_signature, QuoteTypeNode):
            return
        for parameter in quote_signature.captures:
            validate_type_v1(parameter.type_node, forbid_quote=forbid_quote)
        for parameter in quote_signature.inputs:
            validate_type_v1(parameter.type_node, forbid_quote=forbid_quote)
        for parameter in quote_signature.outputs:
            validate_type_v1(parameter.type_node, forbid_quote=forbid_quote)
        return

    if forbid_quote:
        if type_node.name in _ABI_SCALAR_TYPES_V1:
            if type_node.args:
                raise HostABIError(f"type is not ABI-compatible in v1: {type_node.name}")
            return

        if type_node.name == "List":
            if len(type_node.args) != 1 or not isinstance(type_node.args[0], TypeNode):
                raise HostABIError("type is not ABI-compatible in v1: List")
            validate_type_v1(type_node.args[0], forbid_quote=True)
            return

        if type_node.name == "Map":
            if len(type_node.args) != 2:
                raise HostABIError("type is not ABI-compatible in v1: Map")
            key_type = type_node.args[0]
            value_type = type_node.args[1]
            if not isinstance(key_type, TypeNode) or not isinstance(value_type, TypeNode):
                raise HostABIError("type is not ABI-compatible in v1: Map")
            if key_type.name not in {"Int", "String", "Bool"}:
                raise HostABIError("Map<K,V> key type must be Int, String, or Bool in v1")
            validate_type_v1(key_type, forbid_quote=True)
            validate_type_v1(value_type, forbid_quote=True)
            return

        if type_node.name == "Result":
            if len(type_node.args) != 2:
                raise HostABIError("type is not ABI-compatible in v1: Result")
            value_type = type_node.args[0]
            error_type = type_node.args[1]
            if not isinstance(value_type, TypeNode) or not isinstance(error_type, TypeNode):
                raise HostABIError("type is not ABI-compatible in v1: Result")
            validate_type_v1(value_type, forbid_quote=True)
            validate_type_v1(error_type, forbid_quote=True)
            return

        raise HostABIError(f"type is not ABI-compatible in v1: {type_node.name}")

    if type_node.name == "Map" and len(type_node.args) == 2:
        key_type = type_node.args[0]
        if isinstance(key_type, TypeNode) and key_type.name not in {"Int", "String", "Bool"}:
            raise HostABIError("Map<K,V> key type must be Int, String, or Bool in v1")

    for argument in type_node.args:
        if isinstance(argument, TypeNode):
            validate_type_v1(argument, forbid_quote=forbid_quote)
            continue
        if isinstance(argument, QuoteTypeNode):
            if forbid_quote:
                raise HostABIError("Quote is forbidden across ABI in v1 (including DirtyQuote)")
            for parameter in argument.captures:
                validate_type_v1(parameter.type_node, forbid_quote=forbid_quote)
            for parameter in argument.inputs:
                validate_type_v1(parameter.type_node, forbid_quote=forbid_quote)
            for parameter in argument.outputs:
                validate_type_v1(parameter.type_node, forbid_quote=forbid_quote)


def _validate_signature_types(signature: SignatureNode, *, forbid_quote: bool) -> None:
    for parameter in signature.inputs:
        validate_type_v1(parameter.type_node, forbid_quote=forbid_quote)
    for parameter in signature.outputs:
        validate_type_v1(parameter.type_node, forbid_quote=forbid_quote)
