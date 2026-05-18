from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from types import MappingProxyType

from .ast_nodes import SignatureNode, Visibility
from .symbols import SymbolTable


@dataclass(slots=True)
class HostABIError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


class BindingAvailability(Enum):
    REQUIRED = auto()
    OPTIONAL = auto()


@dataclass(slots=True)
class HostWord:
    name: str
    signature: SignatureNode
    availability: BindingAvailability = BindingAvailability.REQUIRED


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
            exports.append(
                ExportWord(
                    export_name=symbol.name,
                    internal_name=symbol.qualified_name,
                    signature=symbol.signature,
                )
            )
    return export_contract_from_words(exports)
