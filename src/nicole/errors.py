from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ErrorKind(Enum):
    STATIC = auto()
    RUNTIME_CONTRACT = auto()
    INTEGRATION = auto()
    DOMAIN = auto()


@dataclass(slots=True)
class NicoleError(Exception):
    kind: ErrorKind
    message: str


class StaticError(NicoleError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorKind.STATIC, message)


class RuntimeContractError(NicoleError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorKind.RUNTIME_CONTRACT, message)


class IntegrationError(NicoleError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorKind.INTEGRATION, message)

