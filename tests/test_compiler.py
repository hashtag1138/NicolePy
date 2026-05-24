from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.compiler import NicoleCompiler, compile_path
from nicole.errors import DiagnosticError, DiagnosticPhase
from nicole.pipeline import CheckedProgram
from nicole.resolver import ResolutionError
from nicole.source import MEMORY_SOURCE_PATH


def test_compile_explicit_file_returns_checked_program(tmp_path: Path) -> None:
    source_path = tmp_path / "app.nic"
    source_path.write_text(
        "module @app\n"
        "  : run { -- }\n"
        "  ;\n"
        "end-module\n",
        encoding="utf-8",
    )

    checked = NicoleCompiler().compile(source_path)

    assert isinstance(checked, CheckedProgram)


def test_compile_explicit_file_uses_physical_source_provenance(tmp_path: Path) -> None:
    source_path = tmp_path / "app.nic"
    source_path.write_text(
        "module @app\n"
        "  : run { -- }\n"
        "    unknown-name\n"
        "  ;\n"
        "end-module\n",
        encoding="utf-8",
    )

    with pytest.raises(ResolutionError, match="unresolved name") as exc_info:
        NicoleCompiler().compile(source_path)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.span is not None
    assert diagnostic.span.source.path == str(source_path.resolve())
    assert diagnostic.span.source.path != MEMORY_SOURCE_PATH


def test_compile_directory_input_not_supported(tmp_path: Path) -> None:
    with pytest.raises(DiagnosticError) as exc_info:
        NicoleCompiler().compile(tmp_path)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.phase is DiagnosticPhase.PIPELINE
    assert diagnostic.code == "PIPELINE_DIRECTORY_NOT_SUPPORTED"


def test_compile_missing_file_raises_pipeline_source_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.nic"

    with pytest.raises(DiagnosticError) as exc_info:
        NicoleCompiler().compile_file(missing)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.phase is DiagnosticPhase.PIPELINE
    assert diagnostic.code == "PIPELINE_SOURCE_NOT_FOUND"


def test_compile_wrong_extension_raises_pipeline_unsupported_extension(tmp_path: Path) -> None:
    source_path = tmp_path / "app.txt"
    source_path.write_text(": run { -- } ;\n", encoding="utf-8")

    with pytest.raises(DiagnosticError) as exc_info:
        compile_path(source_path)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.phase is DiagnosticPhase.PIPELINE
    assert diagnostic.code == "PIPELINE_UNSUPPORTED_SOURCE_EXTENSION"
