from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.application import NicoleApplication
from nicole.errors import DiagnosticError
from nicole.runtime import RuntimeError, RuntimeHostBindings


def _write_simple_export_program(path: Path) -> None:
    path.write_text(
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    7\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n",
        encoding="utf-8",
    )


def test_constructor_does_not_compile_and_checked_starts_none() -> None:
    app = NicoleApplication("missing.nic")

    assert app.checked is None


def test_compile_caches_checked_program_and_returns_it(tmp_path: Path) -> None:
    source_path = tmp_path / "app.nic"
    _write_simple_export_program(source_path)
    app = NicoleApplication(source_path)

    checked = app.compile()

    assert app.checked is checked


def test_repeated_compile_updates_checked_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    first = object()
    second = object()
    returned = [first, second]
    compile_calls: list[tuple[tuple[Path, ...], object | None]] = []

    class FakeCompiler:
        def __init__(self, *, host_contract=None) -> None:
            self._host_contract = host_contract

        def compile(self, paths):
            compile_calls.append((tuple(paths), self._host_contract))
            return returned[len(compile_calls) - 1]

    monkeypatch.setattr("nicole.application.NicoleCompiler", FakeCompiler)

    app = NicoleApplication("app.nic")
    result_first = app.compile()
    result_second = app.compile()

    assert result_first is first
    assert result_second is second
    assert app.checked is second
    assert len(compile_calls) == 2


def test_run_lazily_compiles_and_reuses_checked_program(monkeypatch: pytest.MonkeyPatch) -> None:
    checked_value = object()
    compile_calls: list[tuple[tuple[Path, ...], object | None]] = []
    interpreter_checked: list[object] = []

    class FakeCompiler:
        def __init__(self, *, host_contract=None) -> None:
            self._host_contract = host_contract

        def compile(self, paths):
            compile_calls.append((tuple(paths), self._host_contract))
            return checked_value

    class FakeInterpreter:
        def __init__(self, *, checked, runtime_bindings) -> None:
            interpreter_checked.append(checked)

        def run_export(self, export_name: str, *args: object) -> object:
            return (export_name, args)

    monkeypatch.setattr("nicole.application.NicoleCompiler", FakeCompiler)
    monkeypatch.setattr("nicole.application.NicoleInterpreter", FakeInterpreter)

    app = NicoleApplication("app.nic")
    first = app.run("@app.main", 1)
    second = app.run("@app.main", 2)

    assert first == ("@app.main", (1,))
    assert second == ("@app.main", (2,))
    assert len(compile_calls) == 1
    assert interpreter_checked == [checked_value, checked_value]
    assert app.checked is checked_value


def test_run_creates_fresh_interpreter_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    checked_value = object()
    instances: list[object] = []

    class FakeCompiler:
        def __init__(self, *, host_contract=None) -> None:
            self._host_contract = host_contract

        def compile(self, paths):
            return checked_value

    class FakeInterpreter:
        def __init__(self, *, checked, runtime_bindings) -> None:
            instances.append(self)

        def run_export(self, export_name: str, *args: object) -> object:
            return None

    monkeypatch.setattr("nicole.application.NicoleCompiler", FakeCompiler)
    monkeypatch.setattr("nicole.application.NicoleInterpreter", FakeInterpreter)

    app = NicoleApplication("app.nic")
    app.run("@app.main")
    app.run("@app.main")

    assert len(instances) == 2
    assert instances[0] is not instances[1]


def test_mapping_host_bindings_is_accepted() -> None:
    app = NicoleApplication(
        "app.nic",
        host_bindings={"host.console.log": lambda message: message},
    )

    assert isinstance(app._runtime_host_bindings, RuntimeHostBindings)
    assert "host.console.log" in app._runtime_host_bindings.words


def test_mapping_host_bindings_rejects_canonical_host_key() -> None:
    with pytest.raises(RuntimeError, match="runtime host binding must start with 'host.': @host.console.log"):
        NicoleApplication(
            "app.nic",
            host_bindings={"@host.console.log": lambda message: message},
        )


def test_runtime_host_bindings_instance_is_reused() -> None:
    bindings = RuntimeHostBindings({"host.console.log": lambda message: message})
    app = NicoleApplication("app.nic", host_bindings=bindings)

    assert app._runtime_host_bindings is bindings


def test_none_host_bindings_creates_empty_runtime_bindings() -> None:
    app = NicoleApplication("app.nic", host_bindings=None)

    assert isinstance(app._runtime_host_bindings, RuntimeHostBindings)
    assert dict(app._runtime_host_bindings.words) == {}


def test_run_passes_export_name_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_export_names: list[str] = []

    class FakeCompiler:
        def __init__(self, *, host_contract=None) -> None:
            self._host_contract = host_contract

        def compile(self, paths):
            return object()

    class FakeInterpreter:
        def __init__(self, *, checked, runtime_bindings) -> None:
            pass

        def run_export(self, export_name: str, *args: object) -> object:
            seen_export_names.append(export_name)
            return None

    monkeypatch.setattr("nicole.application.NicoleCompiler", FakeCompiler)
    monkeypatch.setattr("nicole.application.NicoleInterpreter", FakeInterpreter)

    app = NicoleApplication("app.nic")
    app.run("@app.main")

    assert seen_export_names == ["@app.main"]


def test_compile_error_propagates_unchanged() -> None:
    app = NicoleApplication("missing.nic")

    with pytest.raises(DiagnosticError):
        app.compile()


def test_runtime_error_propagates_unchanged(tmp_path: Path) -> None:
    source_path = tmp_path / "app.nic"
    _write_simple_export_program(source_path)
    app = NicoleApplication(source_path)

    with pytest.raises(RuntimeError, match="missing export: @app.missing"):
        app.run("@app.missing")
