from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import ClassVar

from .source import SourceFile, SourceSpan

__all__ = [
    "Diagnostic",
    "DiagnosticError",
    "DiagnosticPhase",
    "DiagnosticSeverity",
    "ErrorKind",
    "IntegrationError",
    "NicoleError",
    "RuntimeContractError",
    "StaticError",
]


class DiagnosticSeverity(Enum):
    ERROR = auto()
    WARNING = auto()
    NOTE = auto()


class DiagnosticPhase(Enum):
    LEXER = auto()
    PARSER = auto()
    SYMBOLS = auto()
    RESOLVER = auto()
    CHECKER = auto()
    ABI = auto()
    PIPELINE = auto()


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: DiagnosticSeverity
    phase: DiagnosticPhase
    code: str
    message: str
    span: SourceSpan | None = None
    suggestion: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    cause: BaseException | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("Diagnostic.code must not be empty")
        object.__setattr__(self, "notes", tuple(self.notes))

    @property
    def source_file(self) -> SourceFile | None:
        if self.span is None:
            return None
        return self.span.source

    @property
    def source(self) -> SourceFile | None:
        return self.source_file


class DiagnosticError(Exception):
    phase: ClassVar[DiagnosticPhase] = DiagnosticPhase.PIPELINE
    default_code: ClassVar[str] = "PIPELINE_ERROR"
    include_location_in_str: ClassVar[bool] = True

    diagnostics: tuple[Diagnostic, ...]

    def __init__(
        self,
        message: str | None = None,
        line: int | None = None,
        column: int | None = None,
        *,
        diagnostics: Iterable[Diagnostic] | None = None,
        diagnostic: Diagnostic | None = None,
        code: str | None = None,
        span: SourceSpan | None = None,
        severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
        suggestion: str | None = None,
        notes: Iterable[str] = (),
        cause: BaseException | None = None,
    ) -> None:
        if diagnostics is not None and diagnostic is not None:
            raise TypeError("DiagnosticError cannot accept both diagnostics and diagnostic")

        if diagnostics is not None:
            built_diagnostics = tuple(diagnostics)
            if len(built_diagnostics) != 1:
                raise ValueError("DiagnosticError requires exactly one Diagnostic")
        elif diagnostic is not None:
            built_diagnostics = (diagnostic,)
        else:
            if message is None:
                raise TypeError("DiagnosticError requires message when no Diagnostic is provided")
            built_diagnostics = (
                Diagnostic(
                    severity=severity,
                    phase=self.phase,
                    code=code or self.default_code,
                    message=message,
                    span=span,
                    suggestion=suggestion,
                    notes=tuple(notes),
                    cause=cause,
                ),
            )

        self.diagnostics = built_diagnostics
        self.message = self.diagnostic.message

        resolved_line = line
        if resolved_line is None and self.diagnostic.span is not None:
            resolved_line = self.diagnostic.span.line
        if resolved_line is not None:
            self.line = resolved_line

        resolved_column = column
        if resolved_column is None and self.diagnostic.span is not None:
            resolved_column = self.diagnostic.span.column
        if resolved_column is not None:
            self.column = resolved_column

        super().__init__(self.message)

    @property
    def diagnostic(self) -> Diagnostic:
        return self.diagnostics[0]

    def __str__(self) -> str:
        if not self.include_location_in_str:
            return self.message
        line = getattr(self, "line", None)
        column = getattr(self, "column", None)
        if line is None or column is None:
            return self.message
        return f"{self.message} at {line}:{column}"


class ErrorKind(Enum):
    STATIC = auto()
    RUNTIME_CONTRACT = auto()
    INTEGRATION = auto()
    DOMAIN = auto()


@dataclass(slots=True)
class NicoleError(Exception):
    kind: ErrorKind
    message: str


class StaticError(NicoleError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorKind.STATIC, message)


class RuntimeContractError(NicoleError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorKind.RUNTIME_CONTRACT, message)


class IntegrationError(NicoleError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorKind.INTEGRATION, message)
