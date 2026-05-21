"""
Placeholder module.

Nicole v0.14 uses direct AST execution through `nicole.runtime`.
This module is reserved for future work and is not part of the active execution pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class InstructionKind(Enum):
    PUSH_LITERAL = auto()
    READ_LOCAL = auto()
    CALL = auto()
    IF = auto()
    CASE = auto()
    QUOTE = auto()
    PRIMITIVE = auto()
    HOST_CALL = auto()


@dataclass(slots=True)
class Instruction:
    kind: InstructionKind
    payload: object | None = None


@dataclass(slots=True)
class Block:
    instructions: list[Instruction] = field(default_factory=list)
