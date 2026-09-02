import logging
from pathlib import Path
from typing import Callable

from pokecontrollerext.app.settings import AppSettings
from pokecontrollerext.command.info import CommandInfo
from pokecontrollerext.papico.context import PapicoResult
from pokecontrollerext.papico.delegates.command import (
    PapicoCommandDelegate,
)
from pokecontrollerext.papico.delegates.external_tools import (
    PapicoExternalToolsDelegate,
)
from pokecontrollerext.papico.delegates.settings import (
    PapicoSettingsDelegate,
)
from pokecontrollerext.papico.handlers import (
    PapicoRegisterHandlerContext,
)
from pokecontrollerext.papico.types import (
    PapicoContainer,
    PapicoHandlerGenerator,
)
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)

LATEST_API_VERSION = "0.2.0"

logger = logging.getLogger(__name__)


class Papico:
    """Poke-Controller Public API Compatible Orchestrator

    Poke-Controllerの公開APIのバージョンによって異なる処理を適切に振り分けるクラス。
    それぞれのAPIバージョンに対応したハンドラを定義することで、同一アプリケーション上で
    複数のバージョンのAPIをサポートできるようにしています。
    この仕組みにより、v0.1.8のCommandの動作を維持しつつ、全く新規のバージョンのCommand APIの提供も可能になります。
    """

    _settings_path: Path

    def __init__(self) -> None:
        self._runtime_info = get_app_runtime_info()
        self._handler_generators: PapicoContainer[PapicoHandlerGenerator] = {}

        self._external_tools_delegate = PapicoExternalToolsDelegate(
            latest_api_version=LATEST_API_VERSION,
            handler_generators=self._handler_generators,
        )
        self._settings_delegate = PapicoSettingsDelegate(
            latest_api_version=LATEST_API_VERSION,
            handler_generators=self._handler_generators,
        )
        self._command_delegate = PapicoCommandDelegate(
            latest_api_version=LATEST_API_VERSION,
            handler_generators=self._handler_generators,
        )

    @property
    def settings_path(self) -> Path:
        return self._settings_delegate.settings_path

    def register_handler(self, ctx: PapicoRegisterHandlerContext) -> None:
        self._handler_generators.setdefault(
            ctx.api_version,
            {},
        ).setdefault(
            ctx.domain,
            {},
        )[ctx.operation] = ctx.handler_generator

    def initialize_external_tools(self) -> PapicoResult[None]:
        result = self._external_tools_delegate.initialize()
        if not result.success:
            logger.warning(f"Failed to initialize external tools: {result.error}")
        return result

    def load_settings(self) -> PapicoResult[AppSettings]:
        result = self._settings_delegate.load()
        if not result.success:
            logger.warning(f"Failed to load settings: {result.error}")
        return result

    def reload_settings(self) -> PapicoResult[AppSettings]:
        result = self._settings_delegate.reload()
        if not result.success:
            logger.warning(f"Failed to reload settings: {result.error}")
        return result

    def save_settings(self) -> PapicoResult[None]:
        result = self._settings_delegate.save()
        if not result.success:
            logger.warning(f"Failed to save settings: {result.error}")
        return result

    def initialize_command(self) -> PapicoResult[None]:
        result = self._command_delegate.initialize()
        if not result.success:
            logger.warning(f"Failed to initialize command: {result.error}")
        return result

    def load_commands(self) -> PapicoResult[list[CommandInfo]]:
        result = self._command_delegate.load()
        if not result.success:
            logger.warning(f"Failed to load commands: {result.error}")
        return result

    def start_command(
        self,
        command_info: CommandInfo,
        *,
        post_process: Callable[[], None] | None = None,
        sync_name: str | None = None,
    ) -> PapicoResult[None]:
        result = self._command_delegate.start(
            command_info,
            post_process=post_process,
            sync_name=sync_name,
        )
        if not result.success:
            logger.warning(f"Failed to start command: {result.error}")
        return result

    def stop_command(self) -> PapicoResult[None]:
        result = self._command_delegate.stop()
        if not result.success:
            logger.warning(f"Failed to stop command: {result.error}")
        return result

    def pause_command(self) -> PapicoResult[None]:
        result = self._command_delegate.pause()
        if not result.success:
            logger.warning(f"Failed to pause command: {result.error}")
        return result

    def resume_command(self) -> PapicoResult[None]:
        result = self._command_delegate.resume()
        if not result.success:
            logger.warning(f"Failed to resume command: {result.error}")
        return result
