#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンドの一覧の絞り込み・並び替えと、実行した履歴

画面(tkinter)には触れない。一覧の読み込みと実行は services/command_service.py が行う。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, Container, Iterable

if TYPE_CHECKING:
    from CommandLoader import CommandEntry

# 並び順(既定の順は、読み込んだ順のまま)
SORT_DEFAULT = "default"
HISTORY_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def sort_tags(commands: Iterable[CommandEntry]) -> list:
    """
    コマンドが持つタグの一覧(ディレクトリのタグ(@...)は後半にまとめる)
    """
    tags = set()
    for c in commands:
        tags.update(c.tags)
    return sorted([s for s in tags if s[0] != "@"]) + sorted([s for s in tags if s[0] == "@"])


def filter_commands(
    commands: Iterable[CommandEntry],
    tags: Iterable[str] = (),
    name_filter: str = "",
    sort: str = SORT_DEFAULT,
    mtime_of: Callable[[CommandEntry], float] | None = None,
    usage_of: Callable[[CommandEntry], int] | None = None,
) -> list:
    """
    絞り込みと並び順を適用した一覧を返す: [(元の番号, コマンド), ...]
    tags: 選択されたタグ(いずれかを持つコマンドを残す。空なら絞り込まない)
    name_filter: 名前に含まれる文字(大文字と小文字は区別しない。空なら絞り込まない)
    sort: 並び順("name_asc" / "name_desc" / "mtime_asc" / "mtime_desc" / "usage_desc" / "usage_asc"。
        それ以外は読み込んだ順)
    mtime_of: コマンドの更新日時を返す関数(更新日時で並べる場合に使う。None のときは、読み込んだ順のまま)
    usage_of: コマンドを実行した回数を返す関数(使用頻度で並べる場合に使う。None のときは、読み込んだ順のまま)
    """
    tags = set(tags)
    name_filter = name_filter.strip().lower()
    rows = list(enumerate(commands))
    if sort.startswith("name"):
        rows.sort(key=lambda ic: ic[1].name.lower(), reverse=sort.endswith("desc"))
    elif sort.startswith("mtime") and mtime_of is not None:
        rows.sort(key=lambda ic: mtime_of(ic[1]), reverse=sort.endswith("desc"))
    elif sort.startswith("usage") and usage_of is not None:
        # 回数が同じものは、多い順でも少ない順でも、読み込んだ順のまま並べる
        sign = -1 if sort.endswith("desc") else 1
        rows.sort(key=lambda ic: sign * usage_of(ic[1]))
    result = []
    for i, c in rows:
        if tags and not tags.intersection(c.tags):
            continue
        if name_filter and name_filter not in c.name.lower():
            continue
        result.append((i, c))
    return result


def normalize_command_type(commandtype: str) -> str:
    """
    コマンドの種別の書き方をそろえる("Python" / "Mcu"。それ以外はそのまま返す)
    """
    if commandtype in ["Python", "PYTHON", "python", "Py", "PY", "py"]:
        return "Python"
    elif commandtype in ["Mcu", "MCU", "mcu"]:
        return "Mcu"
    return commandtype


def find_named_command(
    commandtype: str, commandname: str, python_names: Container[str], mcu_names: Container[str]
) -> tuple[str | None, str]:
    """
    種別と名前で指定されたコマンドが一覧にあるかを確かめる。
    (そろえた種別, "") または (None, 見つからない理由) を返す
    python_names / mcu_names: 一覧にある Python コマンド / Mcu コマンドの名前
    """
    commandtype = normalize_command_type(commandtype)
    if commandtype == "Python":
        if commandname not in python_names:
            return None, "Python command name error."
        return "Python", ""
    elif commandtype == "Mcu":
        if commandname not in mcu_names:
            return None, "Mcu command name error."
        return "Mcu", ""
    return None, "command type error."


def add_history(
    history: list, commandtype: str, commandname: str, max_entries: int, now: datetime | None = None
) -> None:
    """
    履歴の先頭に足す(同じコマンドは先頭に移動し、最大件数を超えた古い履歴は削除する)。history を書き換える
    history: 履歴の一覧({"class": 種別, "name": 名前, "last_run": 実行した日時} の list)
    now: 実行した日時(None のときは、今の日時)
    """
    commandtype = normalize_command_type(commandtype)
    history[:] = [h for h in history if not (h["class"] == commandtype and h["name"] == commandname)]
    last_run = (now if now is not None else datetime.now()).strftime(HISTORY_TIME_FORMAT)
    history.insert(0, {"class": commandtype, "name": commandname, "last_run": last_run})
    del history[max_entries:]


def sorted_history(history: list, descending: bool = True) -> list:
    """
    履歴を実行した日時の順に並べる: [(元の番号, 履歴), ...]
    """
    return sorted(enumerate(history), key=lambda ih: ih[1]["last_run"], reverse=descending)
