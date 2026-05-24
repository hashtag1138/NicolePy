from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
import os
from pathlib import Path

from .ast_nodes import ASTNode, ModuleDeclaration, ProgramNode, WordDefNode
from .errors import DiagnosticError, DiagnosticPhase
from .host_abi import HostContract
from .lexer import lex_source
from .parser import Parser
from .pipeline import CheckedProgram, _analyze_program, _analyze_source_file
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
        input_path: str | Path | Iterable[str | Path],
    ) -> CheckedProgram:
        source_paths = self._normalize_inputs(input_path)
        if not source_paths:
            raise CompilerInputError(
                message="no .nic source files were found in the provided compile input",
                code="PIPELINE_EMPTY_SOURCE_SET",
            )
        source_files = tuple(self._load_source_file(path) for path in source_paths)
        if len(source_files) == 1:
            checked = _analyze_source_file(
                source_files[0],
                host_contract=self._host_contract,
            )
            return replace(checked, source_files=source_files)

        parsed_programs = tuple(
            Parser(lex_source(source_file)).parse()
            for source_file in source_files
        )
        merged_program = self._merge_programs(parsed_programs)
        checked = _analyze_program(
            merged_program,
            host_contract=self._host_contract,
        )
        return replace(checked, source_files=source_files)

    def compile_file(
        self,
        file_path: str | Path,
    ) -> CheckedProgram:
        source_file = self._load_source_file(Path(file_path))
        checked = _analyze_source_file(
            source_file,
            host_contract=self._host_contract,
        )
        return replace(checked, source_files=(source_file,))

    def _normalize_inputs(self, input_path: str | Path | Iterable[str | Path]) -> tuple[Path, ...]:
        resolved_files: dict[str, Path] = {}
        for candidate in self._iter_input_paths(input_path):
            if candidate.is_dir():
                for discovered in self._discover_directory_sources(candidate):
                    resolved_files[str(discovered)] = discovered
            else:
                resolved = self._validate_source_file(candidate)
                resolved_files[str(resolved)] = resolved
        return tuple(sorted(resolved_files.values(), key=lambda path: str(path)))

    @staticmethod
    def _iter_input_paths(input_path: str | Path | Iterable[str | Path]) -> Iterable[Path]:
        if isinstance(input_path, (str, Path)):
            return (Path(input_path),)
        return (Path(item) for item in input_path)

    def _discover_directory_sources(self, directory_path: Path) -> tuple[Path, ...]:
        if not directory_path.exists() or not directory_path.is_dir():
            raise CompilerInputError(
                message=f"source path not found: {directory_path}",
                code="PIPELINE_SOURCE_NOT_FOUND",
            )

        discovered: dict[str, Path] = {}
        for root, dirnames, filenames in os.walk(directory_path, topdown=True, followlinks=False):
            root_path = Path(root)
            dirnames[:] = [name for name in dirnames if not (root_path / name).is_symlink()]
            for filename in filenames:
                candidate = root_path / filename
                try:
                    resolved = candidate.resolve()
                except OSError:
                    continue
                if resolved.suffix == ".nic":
                    discovered[str(resolved)] = resolved
        return tuple(sorted(discovered.values(), key=lambda path: str(path)))

    def _load_source_file(self, file_path: Path) -> SourceFile:
        resolved_path = self._validate_source_file(file_path)
        source_text = resolved_path.read_text(encoding="utf-8")
        return SourceFile(str(resolved_path), text=source_text)

    @staticmethod
    def _merge_programs(programs: tuple[ProgramNode, ...]) -> ProgramNode:
        if not programs:
            raise CompilerInputError(
                message="no parsed programs were available for merge",
                code="PIPELINE_EMPTY_SOURCE_SET",
            )
        if len(programs) == 1:
            return programs[0]

        declarations: list[ASTNode] = []
        words: list[WordDefNode] = []
        for program in programs:
            declarations.extend(program.declarations)
            words.extend(NicoleCompiler._module_words(program.declarations))

        return ProgramNode(
            span=programs[0].span,
            declarations=tuple(declarations),
            words=tuple(words),
        )

    @staticmethod
    def _module_words(declarations: tuple[ASTNode, ...]) -> tuple[WordDefNode, ...]:
        words: list[WordDefNode] = []
        for declaration in declarations:
            if not isinstance(declaration, ModuleDeclaration):
                continue
            for item in declaration.items:
                if isinstance(item, WordDefNode):
                    words.append(item)
        return tuple(words)

    def _validate_source_file(self, source_path: Path) -> Path:
        if not source_path.exists() or not source_path.is_file():
            raise CompilerInputError(
                message=f"source file not found: {source_path}",
                code="PIPELINE_SOURCE_NOT_FOUND",
            )
        resolved_path = source_path.resolve()
        if resolved_path.suffix != ".nic":
            raise CompilerInputError(
                message=f"unsupported source extension for explicit compile input: {source_path}",
                code="PIPELINE_UNSUPPORTED_SOURCE_EXTENSION",
            )
        return resolved_path


def compile_path(
    input_path: str | Path | Iterable[str | Path],
    *,
    host_contract: HostContract | None = None,
) -> CheckedProgram:
    return NicoleCompiler(host_contract=host_contract).compile(input_path)
