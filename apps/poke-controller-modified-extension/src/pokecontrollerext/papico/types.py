from typing import Callable

from .handlers.handler import PapicoHandler

type PapicoContainer[T] = dict[str, dict[str, dict[str, T]]]

type PapicoHandlerGenerator = Callable[[], PapicoHandler]
