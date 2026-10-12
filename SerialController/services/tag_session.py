#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
タグの編集画面の中身(画面を持たない版)

コマンドの一覧と、ファイルに書いてあるタグを読み取り(load)、変更をまとめて保存する(save)。
ファイルの読み書きは services/tag_editor.py が行う。ここでは、画面(Web 版のブラウザ)に渡す形にまとめる。
保存していない変更は、画面の側が持つ(ここでは持たない)。画面(tkinter)には触れない。
"""
from __future__ import annotations

import os
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

from services import tag_editor
from services.tag_editor import CHANGED, TagEditError, TagSource

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

COMMAND_TYPES = ("Python", "Mcu")


class TagEditorSession:
    """
    タグの編集の 1 回分(画面を開いてから閉じるまで)
    """

    def __init__(self, get_entries: Callable[[str], list], on_saved: Callable[[], None] | None = None):
        """
        get_entries: コマンドの種類("Python" / "Mcu")から、今のコマンドの一覧(CommandEntry)を返す関数
        on_saved: 保存した後に呼ぶ関数(コマンドの一覧を読み直すのに使う)
        """
        self.get_entries = get_entries
        self.on_saved = on_saved
        # キー(種類, コマンドの名前)ごとの、クラスの名前・ファイルの状態・編集前のタグ・フォルダーのタグ
        self.class_names: dict[tuple, str] = {}
        self.sources: dict[tuple, TagSource] = {}
        self.initial: dict[tuple, list] = {}
        self.folder_tags: dict[tuple, list] = {}

    def load(self) -> dict:
        """
        コマンドの一覧と、ファイルに書いてあるタグを読み直して、画面に渡す形で返す:
        {"types": [種類], "commands": {種類: [{"name", "tags", "folder_tags", "editable", "reason"}, ...]}}
        """
        self.class_names, self.sources, self.initial, self.folder_tags = {}, {}, {}, {}
        commands = {}
        for command_type in COMMAND_TYPES:
            rows = []
            for entry in self.get_entries(command_type):
                key = (command_type, entry.name)
                own, folder = tag_editor.split_entry_tags(entry)
                path = os.path.abspath(entry.file_path) if entry.file_path else ""
                source = tag_editor.read_source(path, entry.class_name)
                self.class_names[key] = entry.class_name
                self.sources[key] = source
                # 一覧に出ているタグ(同じファイルの基底クラスから引き継いだものを含む)を、編集前のタグとする
                self.initial[key] = [str(tag) for tag in own]
                self.folder_tags[key] = [str(tag) for tag in folder]
                rows.append(
                    {
                        "name": entry.name,
                        "tags": list(self.initial[key]),
                        "folder_tags": list(self.folder_tags[key]),
                        "editable": source.editable,
                        "reason": source.reason,
                    }
                )
            commands[command_type] = rows
        return {"types": list(COMMAND_TYPES), "commands": commands}

    def _check(self, key: tuple, tags: object) -> str:
        """変更の内容を確かめる。保存できない理由を返す(保存できるなら空文字)"""
        if key not in self.sources:
            return "コマンドが見つかりません(一覧が変わっています)。"
        if not self.sources[key].editable:
            return f"このコマンドのタグは編集できません。{self.sources[key].reason}"
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            return "タグの指定が正しくありません。"
        checked = list(self.folder_tags[key])
        for tag in tags:
            stripped, error = tag_editor.check_tag(tag, checked)
            if error or stripped != tag:
                return error or f"「{tag}」の前後に、空白があります。"
            checked.append(tag)
        return ""

    def save(self, changes: list) -> dict:
        """
        変更したコマンドのファイルを書き換える(同じファイルのコマンドは、まとめて 1 回で書く)。
        changes: [{"command_type", "name", "tags"}, ...]
        戻り値: {"saved": 保存した件数, "failures": [保存できなかった理由], "kept": [[種類, 名前], ...], "state": 読み直した内容}
        kept は、書き込めなかっただけのもの(画面の側は、その変更を残す。原因を取り除いて、もう一度保存できる)。
        画面を開いた後に書き換えられていたファイルは、上書きせず、その変更は残さない(今の内容を読み直す)
        """
        files: dict[str, dict] = {}
        failures, kept = [], []
        for change in changes if isinstance(changes, list) else []:
            if not isinstance(change, dict):
                continue
            key = (str(change.get("command_type")), str(change.get("name")))
            tags = change.get("tags")
            error = self._check(key, tags)
            if error:
                failures.append(f"・{key[1]}\n  {error}")
                kept.append(list(key))
                continue
            if tags != self.initial[key]:
                files.setdefault(self.sources[key].file_path, {})[key] = tags
        saved = 0
        for path, file_changes in files.items():
            digest = self.sources[next(iter(file_changes))].digest
            try:
                tag_editor.save_tags(path, digest, {self.class_names[key]: tags for key, tags in file_changes.items()})
            except TagEditError as error:
                names = "、".join(key[1] for key in file_changes)
                failures.append(f"・{names}\n  {os.path.basename(path)}: {error}")
                _logger.warning(f"Failed to save tags: {path} ({error.kind}: {error})")
                if error.kind != CHANGED:
                    kept.extend([list(key) for key in file_changes])
            else:
                saved += len(file_changes)
        # コマンドの一覧も、今のファイルの内容に合わせる(保存できなかったファイルが、書き換えられていた場合を含む)
        if self.on_saved is not None:
            self.on_saved()
        return {"saved": saved, "failures": failures, "kept": kept, "state": self.load()}
