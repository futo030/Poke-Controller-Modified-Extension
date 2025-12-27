from dataclasses import dataclass
from typing import Callable

from pokecontrollerext.papico.context import PapicoContext
from pokecontrollerext.papico.handlers.handler import PapicoHandler


@dataclass(frozen=True, kw_only=True)
class PapicoRegisterHandlerContext(PapicoContext):
    handler_generator: Callable[[], PapicoHandler]
