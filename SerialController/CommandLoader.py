#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from typing import Any

import Utility as util

from logging import getLogger, DEBUG, NullHandler

logger = getLogger(__name__)
logger.addHandler(NullHandler())
logger.setLevel(DEBUG)
logger.propagate = True


@dataclass
class CommandEntry:
    """
    インポートせずにソースコードから取得したコマンドの情報
    """

    name: str  # 表示名 "NAME (ディレクトリ/ファイル名)"
    tags: list = field(default_factory=list)
    module_name: str = ""
    class_name: str = ""
    file_path: str = ""


class CommandLoader:
    """
    GUI起動時はモジュールをインポートせず、ソースコードを静的解析してコマンドの一覧のみ取得する。
    コマンドの実行時(getCommandClass)に、必要なモジュールのみインポートする。
    """

    def __init__(self, base_path: str, base_class: type) -> None:
        """
        base_path: コマンドを置くフォルダー(SerialController からの相対パス。例: Commands/PythonCommands)
        base_class: コマンドの基底クラス(getCommandClass は、これを継承したクラスだけを返す)
        """
        self.path = base_path
        self.base_type = base_class
        self.package = self.path.replace(os.sep, ".")
        self.entries: list[CommandEntry] = []
        self.module_names: list[str] = []

    def load(self) -> list[CommandEntry]:
        """
        コマンドの一覧を取得する (モジュールはインポートしない)
        """
        self.module_names = util.getModuleNames(self.path)
        self.entries = []
        for mod_name in self.module_names:
            self.entries.extend(self._scanModule(mod_name))
        return self.entries

    def reload(self) -> list[CommandEntry]:
        """
        コマンドの一覧を更新する。削除されたモジュールはアンロードする。
        設定されているコマンドのモジュールの再読み込みは getCommandClass(entry, reload=True) で行う。
        戻り値: 更新した後の一覧
        """
        old_module_names = set(self.module_names)
        entries = self.load()

        # Unload deleted commands
        for mod_name in old_module_names - set(self.module_names):
            if mod_name in sys.modules:
                sys.modules.pop(mod_name)  # Un-import module forcefully
                logger.debug(f"Unload module: {mod_name}")

        return entries

    def findEntry(self, name: str) -> CommandEntry | None:
        """表示名("NAME (ディレクトリ/ファイル名)")が name のコマンドを返す(なければ None)"""
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def getCommandClass(self, entry: CommandEntry, reload: bool = False) -> type:
        """
        コマンドのクラスを取得する。
        モジュールがインポートされていなければ、そのモジュール(および依存モジュール)のみインポートする。
        reload=True の場合は、コマンドフォルダ内の依存モジュールとともに再読み込みする。
        クラスがない、基底クラスを継承していない場合は ImportError(インポート中の例外は、そのまま出る)
        """
        if reload and entry.module_name in sys.modules:
            # 依存しているコマンドフォルダ内のモジュールを先に再読み込みする
            for mod_name in self._getLocalDependencies(entry.module_name):
                if mod_name in sys.modules:
                    logger.debug(f"Reload module: {mod_name}")
                    importlib.reload(sys.modules[mod_name])
            logger.debug(f"Reload module: {entry.module_name}")
            module = importlib.reload(sys.modules[entry.module_name])
        elif entry.module_name in sys.modules:
            module = sys.modules[entry.module_name]
        else:
            logger.debug(f"Import module: {entry.module_name}")
            module = importlib.import_module(entry.module_name)

        cls = getattr(module, entry.class_name, None)
        if cls is None or not isinstance(cls, type) or not issubclass(cls, self.base_type):
            raise ImportError(f"Command class '{entry.class_name}' is not found in {entry.module_name}")

        # 表示名とディレクトリ名のタグを反映する
        cls.NAME = entry.name
        cls.TAGS = list(entry.tags)
        return cls

    def _scanModule(self, mod_name: str) -> list[CommandEntry]:
        """
        モジュールのソースコードを解析し、NAMEを持つクラスの一覧を取得する
        (mod_name: "Commands.PythonCommands.フォルダー.ファイル" の形。読めない・解析できない場合は空)
        """
        file_path = os.path.join(*mod_name.split(".")) + ".py"
        try:
            with open(file_path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)
        except Exception as e:
            logger.warning(f"Failed to parse command file: {file_path} ({e})")
            return []

        # モジュール内のクラス定義から NAME / TAGS を取得する (同一モジュール内の継承も考慮)
        class_defs = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        attr_cache = {}

        def getAttrs(cls_name: str, visiting: tuple[str, ...] = ()) -> dict[str, Any]:
            """
            クラスの NAME / TAGS を {"NAME": ..., "TAGS": ...} で返す(同じファイルの中の基底クラスの分も含む)
            visiting: たどっている途中のクラス名(継承が輪になっていても止まるようにする)
            """
            if cls_name in attr_cache:
                return attr_cache[cls_name]
            node = class_defs[cls_name]
            attrs = {}
            # 基底クラスから継承(後ろの基底クラスから順に上書き = MROに近い優先順位)
            for base in reversed(node.bases):
                if isinstance(base, ast.Name) and base.id in class_defs and base.id not in visiting:
                    attrs.update(getAttrs(base.id, visiting + (cls_name,)))
            for stmt in node.body:
                targets = []
                if isinstance(stmt, ast.Assign):
                    targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                    value = stmt.value
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                    targets = [stmt.target.id]
                    value = stmt.value
                for t in targets:
                    if t in ("NAME", "TAGS"):
                        try:
                            attrs[t] = ast.literal_eval(value)
                        except Exception:
                            logger.warning(f"{t} of {cls_name} in {file_path} is not a literal. It is ignored.")
            attr_cache[cls_name] = attrs
            return attrs

        dir_parts = mod_name.split(".")[2:]
        dir_name = "/".join(dir_parts)
        dir_tags = ["@" + t for t in dir_parts[:-1]]

        entries = []
        # 従来(inspect.getmembers)と同じくクラス名順に並べる
        for cls_name in sorted(class_defs.keys()):
            if not class_defs[cls_name].bases:
                continue
            attrs = getAttrs(cls_name)
            name = attrs.get("NAME")
            if not name or not isinstance(name, str):
                continue

            tags = attrs.get("TAGS")
            if isinstance(tags, (list, tuple)):
                tags = list(tags) + dir_tags
            elif isinstance(tags, str):
                tags = [tags] + dir_tags
            else:
                if tags is not None:
                    logger.debug(f"TAGS Type error: {mod_name} {name} {type(tags)}")
                tags = dir_tags

            entries.append(
                CommandEntry(
                    name=f"{name} ({dir_name})",
                    tags=tags,
                    module_name=mod_name,
                    class_name=cls_name,
                    file_path=file_path,
                )
            )
        return entries

    def _getLocalDependencies(self, mod_name: str) -> list[str]:
        """
        コマンドフォルダ内で mod_name が依存しているモジュールを、依存される側から順に返す (mod_name自身は含まない)
        """
        local_modules = set(self.module_names)
        order = []
        visited = set()

        def visit(name: str) -> None:
            """name が依存しているモジュールを先にたどってから、name を order に足す"""
            if name in visited:
                return
            visited.add(name)
            for dep in self._getImportedModules(name):
                if dep in local_modules:
                    visit(dep)
            order.append(name)

        visit(mod_name)
        return [m for m in order if m != mod_name]

    def _getImportedModules(self, mod_name: str) -> list[str]:
        """
        モジュールのソースコードにある import の、モジュール名の一覧(読めない・解析できない場合は空)。
        from A import B は、A と A.B の両方を入れる(B がモジュールかどうかは、ここでは分からないため)
        """
        file_path = os.path.join(*mod_name.split(".")) + ".py"
        try:
            with open(file_path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)
        except Exception:
            return []

        package = mod_name.rpartition(".")[0]
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    try:
                        base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                    except Exception:
                        continue
                else:
                    base = node.module or ""
                imported.append(base)
                # from package import module の形式
                imported.extend(f"{base}.{alias.name}" for alias in node.names)
        return imported


class CombinedLoader:
    """
    複数の読み込み先を、1つの一覧として扱う(追加の機能が、コマンドの読み込み先を足すときに使う)
    """

    def __init__(self, *loaders: Any):
        """loaders: 読み込み先(load / reload / findEntry / getCommandClass を持つもの)。一覧には、この順に並ぶ"""
        self.loaders = loaders
        self.entries = []

    def load(self) -> list[CommandEntry]:
        """すべての読み込み先の一覧を、つなげて返す"""
        self.entries = [entry for loader in self.loaders for entry in loader.load()]
        return self.entries

    def reload(self) -> list[CommandEntry]:
        """すべての読み込み先を読み直して、一覧をつなげて返す"""
        self.entries = [entry for loader in self.loaders for entry in loader.reload()]
        return self.entries

    def findEntry(self, name: str) -> CommandEntry | None:
        """表示する名前から、項目を探す(前の読み込み先を優先する)。なければ None"""
        for loader in self.loaders:
            entry = loader.findEntry(name)
            if entry is not None:
                return entry
        return None

    def getCommandClass(self, entry: CommandEntry, reload: bool = False) -> type:
        """その項目を持っている読み込み先に、コマンドのクラスを作らせる。どこにもなければ ImportError"""
        for loader in self.loaders:
            if loader.findEntry(entry.name) is entry:
                return loader.getCommandClass(entry, reload=reload)
        raise ImportError(f"Command '{entry.name}' is not found")
