#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンドから開くダイアログ(tkinter での表示)
"""
from __future__ import annotations

import tkinter as tk

from typing import TYPE_CHECKING

from PokeConDialogue import PokeConDialogue
from UiDispatcher import UiDispatcher

if TYPE_CHECKING:
    from Commands.CommandBase import Command


def open_dialogue(
    command: Command,
    title: str,
    message: int | str | list,
    desc: str | None = None,
    need: type = list,
    mode: int = 0,
    pos: int = 2,
) -> list | dict | bool:
    """
    ダイアログを表示して入力結果を返す
    ダイアログの生成・待機・結果取得はメインスレッドで行い、呼び出し元スレッドは結果を待つだけにする
    command: ダイアログを開くコマンド(表示中のウィンドウを command.message_dialogue に入れる)
    title: ダイアログのウィンドウ名
    message: 入力欄の内容(mode=0: 項目名、またはそのリスト / mode=1: 部品の定義のリスト。PokeConDialogue.py を参照)
    desc: ダイアログの上部に表示する説明(None: 表示しない)
    need: 戻り値の型(list または dict)
    mode: 0: Entryのみ / 1: 部品の定義のリストから作る
    pos: OK / Cancel ボタンの位置(PokeConDialogue.py を参照)
    戻り値: 入力結果(need の型)。キャンセルした場合は False
    """

    def _open() -> list | dict | bool:
        """メインスレッドでダイアログを開き、閉じられるまで待って、入力結果を返す"""
        command.message_dialogue = tk.Toplevel()
        try:
            return PokeConDialogue(command.message_dialogue, title, message, desc=desc, mode=mode, pos=pos).ret_value(need)
        finally:
            command.message_dialogue = None

    return UiDispatcher.call(_open)
