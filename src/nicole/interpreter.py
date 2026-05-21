"""
Placeholder module.

Nicole v0.14 uses direct AST execution through `nicole.runtime`.
This module is reserved for future work and is not part of the active execution pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ir import Block


@dataclass(slots=True)
class Interpreter:
    """Reserved placeholder interpreter for inactive IR scaffolding."""

    def execute(self, block: Block) -> object:
        raise NotImplementedError("Interpreter is not implemented yet.")
