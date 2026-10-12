#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import inspect
import os
from glob import glob
from types import ModuleType
from os.path import join, relpath
from logging import getLogger, DEBUG, NullHandler

logger = getLogger(__name__)
logger.addHandler(NullHandler())
logger.setLevel(DEBUG)
logger.propagate = True


def ospath(path: str) -> str:
    """パスの区切りの "/" を、OS の区切りの文字に変える"""
    return path.replace("/", os.sep)


# Show all file names under the directory
def browseFileNames(path: str = ".", ext: str = "", recursive: bool = True, name_only: bool = True) -> list[str]:
    """
    フォルダーの中のファイル(とフォルダー)の名前の一覧を返す
    path: 探すフォルダー、ext: 名前の終わりの文字(拡張子。例: ".py"。空なら、すべて)
    recursive: 下の階層も探すか、name_only: path からの相対パスで返すか(False なら、path を含むパス)
    """
    search_path = join(path, "**") if recursive else path
    search_path = join(search_path, "*" + ext)

    if name_only:
        return [relpath(f, path) for f in glob(search_path, recursive=recursive)]
    else:
        return glob(search_path, recursive=recursive)


def getClassesInModule(module: ModuleType) -> list[type]:
    """モジュールにあるクラスの一覧(そのモジュールが import したクラスも含む。名前の順)"""
    classes = []
    for members in inspect.getmembers(module, inspect.isclass):
        classes.append(members[1])
    return classes


def getModuleNames(base_path: str) -> list[str]:
    """フォルダー(下の階層を含む)にある .py の、モジュール名の一覧(例: "Commands.PythonCommands.Sample")"""
    filenames = browseFileNames(path=base_path, ext=".py", name_only=False)
    return [name[:-3].replace(os.sep, ".") for name in filenames]


def importAllModules(base_path: str, mod_names: list[str] | None = None) -> list[ModuleType]:
    """
    モジュールを import して、その一覧を返す
    mod_names: import するモジュール名(None なら、base_path にあるすべての .py)
    """
    modules = []
    for name in getModuleNames(base_path) if mod_names is None else mod_names:
        logger.debug(f"Import module: {name}")
        modules.append(importlib.import_module(name))

    return modules


def _default_open_program(path: str) -> str:
    """
    Windowsで、pathを「開く」ときに使われるプログラムのファイル名(小文字)を返す(分からない場合は"")
    """
    return os.path.basename(_default_open_program_path(path)).lower()


def _default_open_program_path(path: str) -> str:
    """
    Windowsで、pathを「開く」ときに使われるプログラムのパスを返す(分からない場合は"")
    """
    import ctypes

    ext = os.path.splitext(path)[1]
    size = ctypes.c_ulong(1024)
    buf = ctypes.create_unicode_buffer(size.value)
    # ASSOCF_NONE = 0, ASSOCSTR_EXECUTABLE = 2
    result = ctypes.windll.shlwapi.AssocQueryStringW(0, 2, ext, "open", buf, ctypes.byref(size))
    return buf.value if result == 0 else ""


def open_text_file(path: str, line: int | None = None) -> None:
    """
    テキストファイル(コマンドの.pyなど)をエディタで開く
    .py を「開く」とPythonで実行される設定の場合は、実行せずに「編集」(なければメモ帳)で開く
    line: 開く行(VS Codeで開く場合のみ、その行の位置で開く)
    """
    import platform
    import subprocess

    system = platform.system()
    if system == "Windows":
        program_path = _default_open_program_path(path)
        program = os.path.basename(program_path).lower()
        if line is not None and program == "code.exe":
            subprocess.Popen([program_path, "-g", f"{path}:{int(line)}"])
            return
        if program and program not in ("python.exe", "pythonw.exe", "py.exe", "pyw.exe"):
            os.startfile(path)
            return
        try:
            os.startfile(path, "edit")
        except OSError:
            subprocess.Popen(["notepad.exe", path])
    elif system == "Darwin":
        subprocess.Popen(["open", "-t", path])
    else:
        subprocess.Popen(["xdg-open", path])
