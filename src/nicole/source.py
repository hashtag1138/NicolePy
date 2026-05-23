from __future__ import annotations

from dataclasses import dataclass
import os

__all__ = [
    "BUILTIN_SOURCE_PATH",
    "HOST_CONTRACT_SOURCE_PATH",
    "MEMORY_SOURCE_PATH",
    "SYNTHETIC_SOURCE_PATH",
    "SourceFile",
    "SourceLocation",
    "SourceSpan",
]

MEMORY_SOURCE_PATH = "<memory>"
SYNTHETIC_SOURCE_PATH = "<synthetic>"
BUILTIN_SOURCE_PATH = "<builtin>"
HOST_CONTRACT_SOURCE_PATH = "<host-contract>"


def _normalize_path(path: str) -> str:
    if path.startswith("<") and path.endswith(">"):
        return path
    return os.path.normpath(path)


@dataclass(frozen=True, slots=True, init=False)
class SourceFile:
    path: str
    normalized_path: str
    text: str | None

    def __init__(self, path: str, *, text: str | None = None) -> None:
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "normalized_path", _normalize_path(path))
        object.__setattr__(self, "text", text)

    @classmethod
    def memory(cls, text: str) -> SourceFile:
        return cls(MEMORY_SOURCE_PATH, text=text)

    @classmethod
    def synthetic(cls) -> SourceFile:
        return cls(SYNTHETIC_SOURCE_PATH, text=None)

    @classmethod
    def builtin(cls) -> SourceFile:
        return cls(BUILTIN_SOURCE_PATH, text=None)

    @classmethod
    def host_contract(cls) -> SourceFile:
        return cls(HOST_CONTRACT_SOURCE_PATH, text=None)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    line: int
    column: int
    offset: int


_DEFAULT_SYNTHETIC_SOURCE = SourceFile.synthetic()


@dataclass(frozen=True, slots=True, init=False)
class SourceSpan:
    source: SourceFile
    start: SourceLocation
    end: SourceLocation

    def __init__(
        self,
        line: int | None = None,
        column: int | None = None,
        offset: int | None = None,
        *,
        source: SourceFile | None = None,
        start: SourceLocation | None = None,
        end: SourceLocation | None = None,
    ) -> None:
        uses_legacy_ctor = line is not None or column is not None or offset is not None
        uses_range_ctor = source is not None or start is not None or end is not None

        if uses_legacy_ctor and uses_range_ctor:
            raise TypeError("SourceSpan() cannot mix legacy and range arguments")

        if uses_range_ctor:
            if source is None or start is None or end is None:
                raise TypeError("SourceSpan() range construction requires source, start, and end")
            self._validate_locations(start, end)
            object.__setattr__(self, "source", source)
            object.__setattr__(self, "start", start)
            object.__setattr__(self, "end", end)
            return

        if line is None or column is None or offset is None:
            raise TypeError("SourceSpan() requires either (line, column, offset) or (source, start, end)")
        location = SourceLocation(line=line, column=column, offset=offset)
        object.__setattr__(self, "source", _DEFAULT_SYNTHETIC_SOURCE)
        object.__setattr__(self, "start", location)
        object.__setattr__(self, "end", location)

    @staticmethod
    def _validate_locations(start: SourceLocation, end: SourceLocation) -> None:
        if start.offset < 0 or end.offset < 0:
            raise ValueError("SourceSpan offsets must be >= 0")
        if start.line < 0 or end.line < 0:
            raise ValueError("SourceSpan lines must be >= 0")
        if start.column < 0 or end.column < 0:
            raise ValueError("SourceSpan columns must be >= 0")
        if end.offset < start.offset:
            raise ValueError("SourceSpan end must be at or after start")

    @property
    def line(self) -> int:
        return self.start.line

    @property
    def column(self) -> int:
        return self.start.column

    @property
    def offset(self) -> int:
        return self.start.offset
