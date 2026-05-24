from __future__ import annotations

from pathlib import Path

from .errors import DiagnosticError, DiagnosticPhase
from .host_abi import HostContract
from .pipeline import CheckedProgram, _analyze_source_file
from .source import SourceFile

__all__ = ["NicoleCompiler", "compile_path"]


class CompilerInputError(DiagnosticError):
    phase = DiagnosticPhase.PIPELINE
    include_location_in_str = False


class NicoleCompiler:
    def __init__(
        self,
        *,
        host_contract: HostContract | None = None,
    ) -> None:
        self._host_contract = host_contract

    def compile(
        self,
        input_path: str | Path,
    ) -> CheckedProgram:
        return self.compile_file(input_path)

    def compile_file(
        self,
        file_path: str | Path,
    ) -> CheckedProgram:
        path = Path(file_path)
        if path.is_dir():
            raise CompilerInputError(
                message="directory input is not supported in Phase 4C; recursive directory loading is planned for later Phase 4 work",
                code="PIPELINE_DIRECTORY_NOT_SUPPORTED",
            )
        if not path.exists():
            raise CompilerInputError(
                message=f"source file not found: {path}",
                code="PIPELINE_SOURCE_NOT_FOUND",
            )
        if path.suffix != ".nic":
            raise CompilerInputError(
                message=f"unsupported source extension for explicit compile input: {path}",
                code="PIPELINE_UNSUPPORTED_SOURCE_EXTENSION",
            )
        resolved_path = path.resolve()
        source_text = resolved_path.read_text(encoding="utf-8")
        source_file = SourceFile(str(resolved_path), text=source_text)
        return _analyze_source_file(
            source_file,
            host_contract=self._host_contract,
        )


def compile_path(
    input_path: str | Path,
    *,
    host_contract: HostContract | None = None,
) -> CheckedProgram:
    return NicoleCompiler(host_contract=host_contract).compile(input_path)
