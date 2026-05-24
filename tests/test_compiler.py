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


def test_recursive_directory_discovery_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path
    nested = root / "nested"
    nested.mkdir()
    file_a = root / "a.nic"
    file_b = nested / "b.nic"
    file_a.write_text("module @a\nend-module\n", encoding="utf-8")
    file_b.write_text("module @b\nend-module\n", encoding="utf-8")

    normalized = NicoleCompiler()._normalize_inputs(root)

    assert normalized == (file_a.resolve(), file_b.resolve())


def test_duplicate_input_paths_are_deduplicated(tmp_path: Path) -> None:
    file_path = tmp_path / "app.nic"
    file_path.write_text("module @app\nend-module\n", encoding="utf-8")

    normalized = NicoleCompiler()._normalize_inputs([file_path, file_path.resolve()])

    assert normalized == (file_path.resolve(),)


def test_directory_symlink_is_not_traversed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = tmp_path / "target"
    root.mkdir()
    target.mkdir()
    file_a = root / "a.nic"
    file_a.write_text("module @a\nend-module\n", encoding="utf-8")
    (target / "hidden.nic").write_text("module @hidden\nend-module\n", encoding="utf-8")
    link = root / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink directories unavailable: {exc}")

    normalized = NicoleCompiler()._normalize_inputs(root)

    assert normalized == (file_a.resolve(),)


def test_compile_directory_with_no_nic_raises_empty_source_set(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not nic", encoding="utf-8")

    with pytest.raises(DiagnosticError) as exc_info:
        NicoleCompiler().compile(tmp_path)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.phase is DiagnosticPhase.PIPELINE
    assert diagnostic.code == "PIPELINE_EMPTY_SOURCE_SET"


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


def test_mixed_iterable_inputs_normalize_to_deterministic_set(tmp_path: Path) -> None:
    file_root = tmp_path / "a.nic"
    source_dir = tmp_path / "dir"
    source_dir.mkdir()
    file_nested = source_dir / "b.nic"
    file_root.write_text("module @a\nend-module\n", encoding="utf-8")
    file_nested.write_text("module @b\nend-module\n", encoding="utf-8")

    normalized = NicoleCompiler()._normalize_inputs([file_root, source_dir])

    assert normalized == (file_root.resolve(), file_nested.resolve())


def test_multiple_discovered_files_raise_multifile_not_implemented(tmp_path: Path) -> None:
    (tmp_path / "a.nic").write_text("module @a\nend-module\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.nic").write_text("module @b\nend-module\n", encoding="utf-8")

    with pytest.raises(DiagnosticError) as exc_info:
        NicoleCompiler().compile(tmp_path)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.phase is DiagnosticPhase.PIPELINE
    assert diagnostic.code == "PIPELINE_MULTIFILE_NOT_IMPLEMENTED"
