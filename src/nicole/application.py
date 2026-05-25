from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from .compiler import NicoleCompiler
from .host_abi import HostContract
from .interpreter import NicoleInterpreter
from .pipeline import CheckedProgram
from .runtime import RuntimeHostBindings

__all__ = ["NicoleApplication"]


class NicoleApplication:
    def __init__(
        self,
        paths: str | Path | Iterable[str | Path],
        *,
        host_contract: HostContract | None = None,
        host_bindings: Mapping[str, Callable[..., object]] | RuntimeHostBindings | None = None,
    ) -> None:
        self._paths = self._normalize_paths(paths)
        self._host_contract = host_contract
        self._runtime_host_bindings = self._normalize_host_bindings(host_bindings)
        self._checked: CheckedProgram | None = None

    @property
    def checked(self) -> CheckedProgram | None:
        return self._checked

    def compile(self) -> CheckedProgram:
        checked = NicoleCompiler(host_contract=self._host_contract).compile(self._paths)
        self._checked = checked
        return checked

    def run(self, export_name: str, *args: object) -> object:
        checked = self._checked if self._checked is not None else self.compile()
        interpreter = NicoleInterpreter(
            checked=checked,
            runtime_bindings=self._runtime_host_bindings,
        )
        return interpreter.run_export(export_name, *args)

    @staticmethod
    def _normalize_paths(paths: str | Path | Iterable[str | Path]) -> tuple[Path, ...]:
        if isinstance(paths, (str, Path)):
            return (Path(paths),)
        return tuple(Path(path) for path in paths)

    @staticmethod
    def _normalize_host_bindings(
        host_bindings: Mapping[str, Callable[..., object]] | RuntimeHostBindings | None,
    ) -> RuntimeHostBindings:
        if host_bindings is None:
            return RuntimeHostBindings({})
        if isinstance(host_bindings, RuntimeHostBindings):
            return host_bindings
        return RuntimeHostBindings(host_bindings)
