from __future__ import annotations

from dataclasses import dataclass

from .pipeline import CheckedProgram
from .runtime import RuntimeHostBindings, _run_export_checked

__all__ = ["NicoleInterpreter"]


@dataclass(frozen=True, slots=True)
class NicoleInterpreter:
    checked: CheckedProgram
    runtime_bindings: RuntimeHostBindings

    def run_export(self, export_name: str, *args: object) -> object:
        return _run_export_checked(
            self.checked,
            export_name,
            self.runtime_bindings,
            args,
        )
