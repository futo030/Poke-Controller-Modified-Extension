import logging
from typing import Any

from pokecontrollerext.papico.context import (
    PapicoExecContext,
    PapicoFailure,
    PapicoResult,
    PapicoSuccess,
)
from pokecontrollerext.papico.exception import PapicoExecException
from pokecontrollerext.papico.handlers.handler import PapicoHandler
from pokecontrollerext.papico.types import (
    PapicoContainer,
    PapicoHandlerGenerator,
)

logger = logging.getLogger(__name__)


class PapicoExternalToolsDelegate:
    def __init__(
        self,
        latest_api_version: str,
        handler_generators: PapicoContainer[PapicoHandlerGenerator],
    ) -> None:
        self._handler_generators = handler_generators
        self._latest_api_version = latest_api_version
        self._domain = "external_tools"

        self._api_versions = ("0.1.8",)

    def initialize(self) -> PapicoResult[None]:
        operation = "initialize"

        for api_version in self._api_versions:
            ctx = self._create_context(
                api_version=api_version,
                operation=operation,
            )
            try:
                handler = self._get_handler(ctx=ctx)
                handler.handle(ctx)
            except KeyError:
                continue
            except Exception as e:
                return PapicoFailure(
                    ctx=self._create_context(
                        api_version=api_version,
                        operation=operation,
                    ),
                    error=PapicoExecException(f"{e}"),
                )

        return PapicoSuccess(
            ctx=self._create_context(
                api_version=self._latest_api_version,
                operation=operation,
            ),
            data=None,
        )

    def _create_context(
        self,
        api_version: str,
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> PapicoExecContext:
        return PapicoExecContext(
            api_version=api_version,
            domain=self._domain,
            operation=operation,
            params=params,
        )

    def _get_handler(self, ctx: PapicoExecContext) -> PapicoHandler:
        return self._handler_generators[ctx.api_version][ctx.domain][ctx.operation]()
