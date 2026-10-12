#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Note(利用者が自由に書けるメモ)の読み書き

画面(tkinter)には触れない。プロファイルごとに、設定ファイルと同じフォルダーの note.txt に保存する。
"""
from __future__ import annotations

import os
from logging import getLogger, DEBUG, NullHandler

from services.settings_store import AppSettings

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

FILE_NAME = "note.txt"


def note_path() -> str:
    """今のプロファイルの、Note のファイルの場所(設定ファイルと同じフォルダー)"""
    return os.path.join(os.path.dirname(os.path.abspath(AppSettings.SETTING_PATH)), FILE_NAME)


def load(path: str | None = None) -> str:
    """Note の内容を読む(ファイルがない・読めないときは、空文字。改行は \\n にそろえる)"""
    path = path or note_path()
    try:
        with open(path, encoding="utf-8-sig", newline="") as file:
            return file.read().replace("\r\n", "\n").replace("\r", "\n")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as error:
        _logger.warning(f"Failed to read the note: {error}")
        return ""


def save(text: str, path: str | None = None) -> bool:
    """
    Note の内容を書く(別の名前で書いてから置き換えるので、途中で止まっても、元のファイルは壊れない)。
    書けたかを返す(書けないときは、ログに残す)。空にした場合は、空のファイルにする
    """
    path = path or note_path()
    temporary = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temporary, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
        os.replace(temporary, path)
        return True
    except OSError as error:
        _logger.warning(f"Failed to save the note: {error}")
        return False
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass
