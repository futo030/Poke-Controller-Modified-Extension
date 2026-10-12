#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tkinter の画面で使う設定

設定ファイルの読み込みと保存は services/settings_store.py の AppSettings が行う(tkinter に依存しない)。
GuiSettings は、画面の部品と結び付ける項目を、tkinter の変数(IntVar / StringVar / BooleanVar)として持つ。
"""
from __future__ import annotations

import os
import tkinter as tk
from typing import Any

from services.settings_store import VARIABLE_FIELDS, AppSettings

_VARIABLE_TYPES = {int: tk.IntVar, str: tk.StringVar, bool: tk.BooleanVar}
_VARIABLE_NAMES = frozenset(name for name, _ in VARIABLE_FIELDS)


class GuiSettings(AppSettings):
    """tkinter の画面で使う設定(画面の部品と結び付ける項目を、tkinter の変数として持つ)"""

    SETTING_PATH = os.path.join(os.path.dirname(__file__), "profiles", "default", "settings.ini")

    def __init__(self):
        """設定ファイルを読み込み、画面の部品と結び付ける項目を、tkinter の変数に置き換える"""
        super().__init__()
        # 画面の部品と結び付ける項目を、読み込んだ値を入れた tkinter の変数に置き換える
        for name, kind in VARIABLE_FIELDS:
            setattr(self, name, _VARIABLE_TYPES[kind](value=getattr(self, name)))
        # Shortcutのコマンド名(ボタンの文字に使う)
        self.command_name_dict = {number: tk.StringVar(value=name) for number, name in self.command_name_dict.items()}

    def _value(self, name: str) -> Any:
        """保存する値(tkinter の変数にした項目は、変数から値を取り出す)"""
        value = getattr(self, name)
        return value.get() if name in _VARIABLE_NAMES else value

    def _shortcut_name(self, number: str) -> str:
        """ショートカットのコマンド名(number: "1"～)を、tkinter の変数から取り出す"""
        return self.command_name_dict[number].get()
