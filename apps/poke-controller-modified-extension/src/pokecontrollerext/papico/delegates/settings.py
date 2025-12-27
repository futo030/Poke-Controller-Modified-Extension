import logging
from pathlib import Path
from typing import Any

from pokecontrollerext.app.settings import AppSettings
from pokecontrollerext.papico.context import (
    PapicoExecContext,
    PapicoFailure,
    PapicoResult,
    PapicoSuccess,
)
from pokecontrollerext.papico.exception import PapicoExecException
from pokecontrollerext.papico.handlers.handler import (
    PapicoHandler,
)
from pokecontrollerext.papico.types import (
    PapicoContainer,
    PapicoHandlerGenerator,
)
from pokecontrollerext.singletons.app.settings import (
    get_app_settings_or_none,
    setup_app_settings,
)
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)

logger = logging.getLogger(__name__)


class PapicoSettingsDelegate:
    _settings_path: Path

    def __init__(
        self,
        latest_api_version: str,
        handler_generators: PapicoContainer[PapicoHandlerGenerator],
    ) -> None:
        self._handler_generators = handler_generators
        self._latest_api_version = latest_api_version
        self._domain = "settings"
        self._app_runtime_info = get_app_runtime_info()

        self._api_versions = (
            "0.2.0",
            "0.1.8",
        )
        self._paths: dict[str, Path] = {
            "0.2.0": (
                self._app_runtime_info.base_dir
                / "profiles"
                / self._app_runtime_info.profile
                / "settings.json"
            ),
            "0.1.8": (
                self._app_runtime_info.base_dir
                / "profiles"
                / self._app_runtime_info.profile
                / "settings.ini"
            ),
        }

    @property
    def settings_path(self) -> Path:
        return self._settings_path

    def load(self) -> PapicoResult[AppSettings]:
        operation = "load"
        if (settings := get_app_settings_or_none()) is not None:
            return PapicoSuccess(
                ctx=self._create_context(
                    api_version=settings.general.version.get(),
                    operation=operation,
                    params={"path": self._settings_path},
                ),
                data=settings,
            )

        for api_version in self._api_versions:
            path = self._paths[api_version]
            if path.exists() and path.is_file():
                logger.info(f"Loading settings from {path}")
                ctx = self._create_context(
                    api_version=api_version,
                    operation=operation,
                    params={"path": path},
                )
                handler = self._get_handler(ctx)
                result = handler.handle(ctx)
                self._settings_path = path
                return result

        ctx = self._create_context(
            api_version=self._latest_api_version,
            operation=operation,
        )
        handler = self._get_handler(ctx)
        result = handler.handle(ctx)
        logger.info("Default settings loaded.")
        return result

    def reload(self) -> PapicoResult[AppSettings]:
        operation = "reload"

        result = self.load()
        if not result.success:
            return PapicoFailure(
                ctx=self._create_context(
                    api_version=result.ctx.api_version,
                    operation=operation,
                ),
                error=result.error,
            )

        if (settings := get_app_settings_or_none()) is None:
            settings = setup_app_settings(result.data)
        else:
            settings.apply_dict(result.data.to_dict())

        return PapicoSuccess(
            ctx=self._create_context(
                api_version=settings.general.version.get(),
                operation=operation,
            ),
            data=settings,
        )

    def save(self) -> PapicoResult[None]:
        operation = "save"
        if (settings := get_app_settings_or_none()) is None:
            return PapicoFailure(
                ctx=self._create_context(
                    api_version=self._latest_api_version,
                    operation=operation,
                ),
                error=PapicoExecException("Settings is not loaded yet."),
            )

        api_version = settings.general.version.get()
        if api_version not in self._paths:
            return PapicoFailure(
                ctx=self._create_context(
                    api_version=self._latest_api_version,
                    operation=operation,
                ),
                error=PapicoExecException(f"Invalid API version: {api_version}"),
            )

        path = self._paths[api_version]
        ctx = self._create_context(
            api_version=api_version,
            operation=operation,
            params={"settings": settings, "path": path},
        )
        handler = self._get_handler(ctx)
        result = handler.handle(ctx)
        logger.info(f"Saving settings to {path}")
        return result

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
