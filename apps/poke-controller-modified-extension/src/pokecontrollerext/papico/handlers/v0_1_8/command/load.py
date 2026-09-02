import logging
from pathlib import Path
from typing import Literal

from pokecontroller.core.dynamic import DynamicClassLoader

from pokecontrollerext.api.v0_1_8.command.commands.mcu.base import (
    McuCommand,
)
from pokecontrollerext.api.v0_1_8.command.commands.python.base import (
    PythonCommand,
)
from pokecontrollerext.command.info import CommandInfo
from pokecontrollerext.papico.context import (
    PapicoExecContext,
    PapicoFailure,
    PapicoResult,
    PapicoSuccess,
)
from pokecontrollerext.papico.exception import (
    PapicoExecException,
)
from pokecontrollerext.papico.handlers.handler import (
    PapicoHandler,
)
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)

logger = logging.getLogger(__name__)


class PapicoCommandLoadHandler(PapicoHandler):
    _base_dir: Path
    _search_root: Path
    _commands: list[CommandInfo]

    def handle(self, ctx: PapicoExecContext) -> PapicoResult[list[CommandInfo]]:
        try:
            app_runtime_info = get_app_runtime_info()
            self._base_dir = app_runtime_info.base_dir
            self._search_root = self._base_dir / "Commands"
            self._commands: list[CommandInfo] = []
            self._load_commands(
                search_root=self._search_root / "PythonCommands",
                super_class=PythonCommand,
                kind="python",
            )
            self._load_commands(
                search_root=self._search_root / "McuCommands",
                super_class=McuCommand,
                kind="mcu",
            )
            return PapicoSuccess(
                ctx=ctx,
                data=self._commands,
            )
        except Exception as e:
            return PapicoFailure(
                ctx=ctx,
                error=PapicoExecException(f"{e}"),
            )

    def _load_commands(
        self,
        search_root: Path,
        super_class: type,
        kind: Literal["python", "mcu"],
    ) -> None:
        for module, name, klass in DynamicClassLoader(  # type: ignore[var-annotated]
            search_root=search_root,
            klass=super_class,
        ).load():
            if klass.NAME == "":
                continue

            module_hierarchy = module.__name__.split(".")
            dir_name = "/".join(module_hierarchy)
            dir_tags = [f"@{t}" for t in module_hierarchy[:-1]]

            tags = []
            if hasattr(klass, "TAGS"):
                if isinstance(klass.TAGS, list):
                    logger.debug(f"TAGS name add: {dir_tags}")
                    tags = klass.TAGS + dir_tags
                elif isinstance(klass.TAGS, str):
                    logger.debug(f"TAGS name add: {dir_tags}")
                    tags = [klass.TAGS] + dir_tags
                else:
                    logger.debug(
                        f"TAGS Type error: {module.__name__} {klass.NAME} {type(klass.TAGS)}"
                    )
            else:
                logger.debug(f"TAGS do not exist: {module.__name__} {klass.NAME}")
                tags += dir_tags

            display_name = f"{klass.NAME} ({dir_name})"

            self._commands.append(
                CommandInfo(
                    name=name,
                    display_name=display_name,
                    tags=tags,
                    module=module,
                    klass=klass,
                    api_version="0.1.8",
                    kind=kind,
                )
            )
