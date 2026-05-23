from __future__ import annotations

from collections.abc import Iterable, Mapping, Set as AbstractSet
from dataclasses import dataclass
from enum import Enum, auto
import re
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
_HOST_OPAQUE_TYPE_RE = re.compile(r"^host\.[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*$")


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


@dataclass(frozen=True, slots=True)
class HostOpaqueType:
    name: str

    def __post_init__(self) -> None:
        _validate_host_opaque_type_name(self.name)


@dataclass(slots=True)
class ExportWord:
    export_name: str
    internal_name: str
    signature: SignatureNode


@dataclass(frozen=True, slots=True)
class HostContract:
    words: Mapping[str, HostWord]
    opaque_types: Mapping[str, HostOpaqueType]


def empty_host_contract() -> HostContract:
    return HostContract(words=MappingProxyType({}), opaque_types=MappingProxyType({}))


def host_contract_from_words(
    words: Iterable[HostWord],
    *,
    opaque_types: Iterable[HostOpaqueType] = (),
) -> HostContract:
    opaque_entries: dict[str, HostOpaqueType] = {}
    for opaque_type in opaque_types:
        if opaque_type.name in opaque_entries:
            raise HostABIError(f"duplicate host opaque type: {opaque_type.name}")
        opaque_entries[opaque_type.name] = opaque_type
    declared_opaque_type_names = frozenset(opaque_entries)

    entries: dict[str, HostWord] = {}
    for word in words:
        if not word.name.startswith("host."):
            raise HostABIError(f"host word name must start with 'host.': {word.name}")
        if word.name in entries:
            raise HostABIError(f"duplicate host word: {word.name}")
        _validate_signature_types(
            word.signature,
            forbid_quote=True,
            declared_opaque_type_names=declared_opaque_type_names,
        )
        entries[word.name] = word

    return HostContract(
        words=MappingProxyType(entries),
        opaque_types=MappingProxyType(opaque_entries),
    )


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


def collect_exports(symbols: SymbolTable, *, host_contract: HostContract | None = None) -> ExportContract:
    declared_opaque_type_names = (
        frozenset(host_contract.opaque_types)
        if host_contract is not None
        else frozenset()
    )
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
            _validate_signature_types(
                symbol.signature,
                forbid_quote=True,
                declared_opaque_type_names=declared_opaque_type_names,
            )
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
    declared_opaque_type_names: AbstractSet[str] = frozenset(),
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
            validate_type_v1(
                parameter.type_node,
                forbid_quote=forbid_quote,
                declared_opaque_type_names=declared_opaque_type_names,
            )
        for parameter in quote_signature.inputs:
            validate_type_v1(
                parameter.type_node,
                forbid_quote=forbid_quote,
                declared_opaque_type_names=declared_opaque_type_names,
            )
        for parameter in quote_signature.outputs:
            validate_type_v1(
                parameter.type_node,
                forbid_quote=forbid_quote,
                declared_opaque_type_names=declared_opaque_type_names,
            )
        return

    if forbid_quote:
        if type_node.name in declared_opaque_type_names:
            if _HOST_OPAQUE_TYPE_RE.match(type_node.name) is None:
                raise HostABIError(f"type is not ABI-compatible in v1: {type_node.name}")
            if type_node.args:
                raise HostABIError(f"type is not ABI-compatible in v1: {type_node.name}")
            return

        if _HOST_OPAQUE_TYPE_RE.match(type_node.name) is not None:
            raise HostABIError(f"undeclared host opaque type in ABI signature: {type_node.name}")

        if type_node.name in _ABI_SCALAR_TYPES_V1:
            if type_node.args:
                raise HostABIError(f"type is not ABI-compatible in v1: {type_node.name}")
            return

        if type_node.name == "List":
            if len(type_node.args) != 1 or not isinstance(type_node.args[0], TypeNode):
                raise HostABIError("type is not ABI-compatible in v1: List")
            validate_type_v1(
                type_node.args[0],
                forbid_quote=True,
                declared_opaque_type_names=declared_opaque_type_names,
            )
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
            validate_type_v1(
                key_type,
                forbid_quote=True,
                declared_opaque_type_names=declared_opaque_type_names,
            )
            validate_type_v1(
                value_type,
                forbid_quote=True,
                declared_opaque_type_names=declared_opaque_type_names,
            )
            return

        if type_node.name == "Result":
            if len(type_node.args) != 2:
                raise HostABIError("type is not ABI-compatible in v1: Result")
            value_type = type_node.args[0]
            error_type = type_node.args[1]
            if not isinstance(value_type, TypeNode) or not isinstance(error_type, TypeNode):
                raise HostABIError("type is not ABI-compatible in v1: Result")
            validate_type_v1(
                value_type,
                forbid_quote=True,
                declared_opaque_type_names=declared_opaque_type_names,
            )
            validate_type_v1(
                error_type,
                forbid_quote=True,
                declared_opaque_type_names=declared_opaque_type_names,
            )
            return

        raise HostABIError(f"type is not ABI-compatible in v1: {type_node.name}")

    if type_node.name == "Map" and len(type_node.args) == 2:
        key_type = type_node.args[0]
        if isinstance(key_type, TypeNode) and key_type.name not in {"Int", "String", "Bool"}:
            raise HostABIError("Map<K,V> key type must be Int, String, or Bool in v1")

    for argument in type_node.args:
        if isinstance(argument, TypeNode):
            validate_type_v1(
                argument,
                forbid_quote=forbid_quote,
                declared_opaque_type_names=declared_opaque_type_names,
            )
            continue
        if isinstance(argument, QuoteTypeNode):
            if forbid_quote:
                raise HostABIError("Quote is forbidden across ABI in v1 (including DirtyQuote)")
            for parameter in argument.captures:
                validate_type_v1(
                    parameter.type_node,
                    forbid_quote=forbid_quote,
                    declared_opaque_type_names=declared_opaque_type_names,
                )
            for parameter in argument.inputs:
                validate_type_v1(
                    parameter.type_node,
                    forbid_quote=forbid_quote,
                    declared_opaque_type_names=declared_opaque_type_names,
                )
            for parameter in argument.outputs:
                validate_type_v1(
                    parameter.type_node,
                    forbid_quote=forbid_quote,
                    declared_opaque_type_names=declared_opaque_type_names,
                )


def _validate_signature_types(
    signature: SignatureNode,
    *,
    forbid_quote: bool,
    declared_opaque_type_names: AbstractSet[str] = frozenset(),
) -> None:
    for parameter in signature.inputs:
        validate_type_v1(
            parameter.type_node,
            forbid_quote=forbid_quote,
            declared_opaque_type_names=declared_opaque_type_names,
        )
    for parameter in signature.outputs:
        validate_type_v1(
            parameter.type_node,
            forbid_quote=forbid_quote,
            declared_opaque_type_names=declared_opaque_type_names,
        )


def _validate_host_opaque_type_name(name: str) -> None:
    if _HOST_OPAQUE_TYPE_RE.match(name) is not None:
        return
    raise HostABIError(f"host opaque type name must be canonical host.*: {name}")
