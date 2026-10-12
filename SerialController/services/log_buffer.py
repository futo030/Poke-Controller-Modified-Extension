#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ログ(コンソールに出しているもの)を、画面に表示するための受け渡し

画面(tkinter)には触れない。
- ログを出す側(どのスレッドでもよい)は、記録を溜めるだけですぐ戻る(文字にするのは、表示するとき)
- 表示する側(画面)は、drain() で溜まった分を受け取り、自分のスレッドで反映する
- 表示する側が受け取らない間は、古いものから捨てる(溜まり続けない)
"""
from __future__ import annotations

import collections
import logging

DEFAULT_MAX_LINES = 10000
# 1 回の drain() で取り出す件数の上限(たくさん溜まっていても、画面を長く止めない。残りは、次の回に取り出す)
DEFAULT_DRAIN_LIMIT = 1000
# コンソールへの出力(PokeConLogger.root_logger)と同じ書き方
LOG_FORMAT = "%(asctime)s %(name)s %(funcName)s [%(levelname)s]: %(message)s"
# 表示するときの、レベルの分け方(色を変える単位): DEBUG 以下 / INFO / WARNING / ERROR 以上
LEVEL_DEBUG = "debug"
LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"


def level_group(levelno: int) -> str:
    """ログのレベル(数)を、表示するときの分け方(LEVEL_DEBUG / LEVEL_INFO / LEVEL_WARNING / LEVEL_ERROR)にする"""
    if levelno >= logging.ERROR:
        return LEVEL_ERROR
    if levelno >= logging.WARNING:
        return LEVEL_WARNING
    if levelno >= logging.INFO:
        return LEVEL_INFO
    return LEVEL_DEBUG


class LogBuffer(logging.Handler):
    """ログの記録を、表示する側が受け取るまで溜めておくハンドラー"""

    def __init__(self, max_lines: int = DEFAULT_MAX_LINES, drain_limit: int = DEFAULT_DRAIN_LIMIT):
        """
        max_lines: 溜めておく件数の上限(超えた分は、古いものから捨てる)
        drain_limit: 1 回の drain() で取り出す件数の上限
        """
        super().__init__(logging.DEBUG)
        self.setFormatter(logging.Formatter(LOG_FORMAT))
        self._drain_limit = drain_limit
        # deque の append / popleft は、ロックなしで複数のスレッドから呼べる
        self._entries = collections.deque(maxlen=max_lines)

    def handle(self, record: logging.LogRecord) -> bool:
        """
        ログの記録を溜める(任意のスレッドから呼ばれる)。
        ハンドラーのロックは取らない(溜めるだけなので要らない。ログを出す側を、待たせない)
        """
        accepted = self.filter(record)
        if accepted:
            self.emit(record)
        return bool(accepted)

    def emit(self, record: logging.LogRecord) -> None:
        """
        記録を溜める。文字にするのは drain() のときに行い、ログを出す側の処理を遅くしない。
        例外つきの記録だけは、ここで文字にする(例外が指しているものを、持ち続けないため)
        """
        if record.exc_info or record.stack_info:
            try:
                self._entries.append((record.levelno, self.format(record)))
            except Exception:
                self.handleError(record)
        else:
            self._entries.append(record)

    def drain(self) -> str:
        """
        溜まった分を、表示する文字(1 件 1 行。コンソールと同じ書き方)にして取り出す。
        1 回に取り出すのは drain_limit 件まで
        """
        return "".join(text for _, text in self.drain_segments())

    def drain_segments(self) -> list:
        """
        溜まった分を、レベルの分け方ごとにまとめて取り出す: [(分け方, 文字), ...]。
        続いている同じ分け方の記録は、1 つにまとめる(文字は、1 件 1 行。コンソールと同じ書き方)。
        1 回に取り出すのは drain_limit 件まで
        """
        segments = []
        group, lines = None, []
        for _ in range(min(len(self._entries), self._drain_limit)):
            try:
                entry = self._entries.popleft()
            except IndexError:
                break
            if isinstance(entry, tuple):
                levelno, text = entry
            else:
                levelno = entry.levelno
                try:
                    text = self.format(entry)
                except Exception:
                    # 書式と引数が合わない記録など(コンソールでも、エラーとして表示されるもの)
                    text = f"{entry.name} [{entry.levelname}]: {entry.msg!r} {entry.args!r}"
            entry_group = level_group(levelno)
            if entry_group != group and lines:
                segments.append((group, "".join(lines)))
                lines = []
            group = entry_group
            lines.append(text + "\n")
        if lines:
            segments.append((group, "".join(lines)))
        return segments

    def clear(self) -> None:
        """溜まっている分を、すべて捨てる"""
        self._entries.clear()

    def __len__(self) -> int:
        """溜まっている件数"""
        return len(self._entries)


# アプリ全体で 1 つ(install() で、ルートのロガーにつなぐ)
buffer = LogBuffer()


def install() -> LogBuffer:
    """ルートのロガーに、画面用のハンドラーをつなぐ(すでにつないでいれば、何もしない)。つないだハンドラーを返す"""
    root = logging.getLogger()
    if buffer not in root.handlers:
        root.addHandler(buffer)
    return buffer
