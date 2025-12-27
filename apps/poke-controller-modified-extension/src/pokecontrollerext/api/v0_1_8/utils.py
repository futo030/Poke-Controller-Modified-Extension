import glob
import importlib
import inspect
import logging
import os
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)


def ospath(path: str) -> str:
    return path.replace("/", os.sep)


def browse_file_names(
    path: str = ".",
    ext: str = "",
    recursive: bool = True,
    name_only: bool = True,
) -> list[str]:
    search_path = os.path.join(path, "**") if recursive else path
    search_path = os.path.join(search_path, "*" + ext)

    if name_only:
        return [
            os.path.relpath(f, path)
            for f in glob.glob(search_path, recursive=recursive)
        ]
    else:
        return glob.glob(search_path, recursive=recursive)


def get_classes_in_module(module: ModuleType) -> list[Any]:
    return [obj for _, obj in inspect.getmembers(module, inspect.isclass)]


def get_module_names(base_path: str) -> list[str]:
    return [
        # 拡張子(.py)を除いてファイルの区切り文字をドット(.)に置き換える
        name[:-3].replace(os.sep, ".")
        for name in browse_file_names(path=base_path, ext=".py", name_only=False)
    ]


def get_all_modules(
    base_path: str, mod_names: list[str] | None = None
) -> list[ModuleType]:
    modules = []
    for name in get_module_names(base_path) if mod_names is None else mod_names:
        logger.debug(f"Import module: {name}")
        modules.append(importlib.import_module(name))
    return modules
