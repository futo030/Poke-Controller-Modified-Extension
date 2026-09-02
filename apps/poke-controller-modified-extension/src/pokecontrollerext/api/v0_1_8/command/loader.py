import importlib
import logging
import sys
from types import ModuleType

from pokecontrollerext.api.v0_1_8.utils import (
    get_all_modules,
    get_classes_in_module,
    get_module_names,
)

logger = logging.getLogger(__name__)


class CommandLoader[T]:
    def __init__(self, base_path: str, base_class: type[T]) -> None:
        self.path: str = base_path
        self.base_type: type[T] = base_class
        self.modules: list[ModuleType] = []

    def load(self) -> list[type[T]]:
        """指定ディレクトリからCommandクラスを動的に読み込む"""
        if self.modules:
            self.modules = get_all_modules(self.path)
        return self._get_command_classes()

    def reload(self) -> list[type[T]]:
        current_modules = {mod.__name__: mod for mod in self.modules}

        current_module_names = set(current_modules.keys())
        renewed_module_names = set(get_module_names(self.path))

        # Load only unloaded modules
        unloaded_module_names = list(renewed_module_names - current_module_names)
        if unloaded_module_names:
            self.modules.extend(get_all_modules(self.path, unloaded_module_names))

        # Reload commands except deleted ones
        old_module_names = list(renewed_module_names & current_module_names)
        for mod_name in old_module_names:
            importlib.reload(current_modules[mod_name])

        # Unload deleted commands
        deleted_module_names = list(current_module_names - renewed_module_names)
        for mod_name in deleted_module_names:
            self.modules.remove(current_modules[mod_name])
            # Un-import module forcefully
            sys.modules.pop(current_modules[mod_name].__name__)

        # return command class types
        return self._get_command_classes()

    # for compatibility
    def getCommandClasses(self) -> list[type[T]]:  # noqa
        return self._get_command_classes()

    def _get_command_classes(self) -> list[type[T]]:
        """self.modulesからbase_typeクラスのサブクラスを取得する"""
        classes = []
        for mod in self.modules:
            class_list = [
                c
                for c in get_classes_in_module(mod)
                if (
                    issubclass(c, self.base_type)
                    and c is not self.base_type
                    and hasattr(c, "NAME")
                    and c.NAME
                )
            ]

            # add TAGS
            for c in class_list:
                dir_name = "/".join(mod.__name__.split(".")[2:])
                dir_tags = ["@" + t for t in mod.__name__.split(".")[2:-1]]

                # add tags of directory name
                if hasattr(c, "TAGS"):
                    if isinstance(c.TAGS, list):
                        logger.debug(f"TAGS name add: {dir_tags}")
                        c.TAGS = c.TAGS + dir_tags
                    elif isinstance(c.TAGS, str):
                        logger.debug(f"TAGS name add: {dir_tags}")
                        c.TAGS = [c.TAGS] + dir_tags
                    else:
                        logger.debug(
                            f"TAGS Type error: {mod.__name__} {c.NAME} {type(c.TAGS)}"
                        )
                else:
                    logger.debug(f"TAGS do not exist: {mod.__name__} {c.NAME}")
                    c.TAGS = dir_tags

                c.NAME = f"{c.NAME} ({dir_name})"
                classes.append(c)

        return classes
