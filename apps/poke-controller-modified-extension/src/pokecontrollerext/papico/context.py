from dataclasses import dataclass
from typing import Any, Literal

from pokecontrollerext.papico.exception import PapicoException


@dataclass(frozen=True, kw_only=True)
class PapicoContext:
    api_version: str
    domain: str
    operation: str


@dataclass(frozen=True, kw_only=True)
class PapicoExecContext(PapicoContext):
    params: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class PapicoSuccess[R]:
    ctx: PapicoExecContext
    data: R
    success: Literal[True] = True
    error: None = None


@dataclass(frozen=True, kw_only=True)
class PapicoFailure:
    ctx: PapicoExecContext
    error: PapicoException
    success: Literal[False] = False
    data: None = None


type PapicoResult[R] = PapicoSuccess[R] | PapicoFailure
