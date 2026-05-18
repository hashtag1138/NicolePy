from __future__ import annotations

from dataclasses import dataclass

from .ir import Block


@dataclass(slots=True)
class Interpreter:
    """Placeholder interpreter for the Nicole IR."""

    def execute(self, block: Block) -> object:
        raise NotImplementedError("Interpreter is not implemented yet.")

