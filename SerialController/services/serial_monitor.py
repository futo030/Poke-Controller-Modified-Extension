#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリアルモニター: 機器へ送ったデータの受け渡し

画面(tkinter)には触れない。
- 送る側(コマンドのスレッドなど)は、add() で溜めてすぐ戻る
- 表示する側(画面)は、drain() で溜まった分をまとめて受け取り、自分のスレッドで反映する
- 表示する側が受け取らない間は、古いものから捨てる(溜まり続けない)
"""
from __future__ import annotations

import collections
import time

DEFAULT_MAX_LINES = 10000


def format_value(value: object) -> str:
    """送ったデータを、表示する文字にする(文字はそのまま。bytes は、空白で区切った 16 進数。そのほかは str にする)"""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex(" ")
    return str(value)


def format_line(stamp: float, format_name: str, value: object) -> str:
    """
    1行の表示(改行つき): [時刻][フォーマット名] 値。
    stamp: 送った時刻(time.time() の値)。時刻は、この PC の時刻で、ミリ秒まで表示する
    """
    # ミリ秒に丸めてから、秒とミリ秒に分ける(繰り上がりで、秒とミリ秒が食い違わないようにする)
    seconds, milliseconds = divmod(int(round(stamp * 1000)), 1000)
    clock = time.strftime("%H:%M:%S", time.localtime(seconds))
    return f"[{clock}.{milliseconds:03d}][{format_name}] {format_value(value)}\n"


class SerialMonitor:
    """機器へ送ったデータを、表示する側が受け取るまで溜めておく"""

    def __init__(self, max_lines: int = DEFAULT_MAX_LINES):
        """
        max_lines: 溜めておく行数の上限(超えた分は、古いものから捨てる)
        """
        # deque の append / popleft は、ロックなしで複数のスレッドから呼べる
        self._entries = collections.deque(maxlen=max_lines)

    def add(self, format_name: str, value: object) -> None:
        """
        送ったデータを溜める(任意のスレッドから呼び出し可能)。時刻は、呼ばれた時点のもの。
        format_name: Data Format の名前。value: 送ったデータ(文字か bytes。そのほかは、ここで文字にする)。
        文字と bytes を表示用の文字にするのは drain() のときに行い、送る側の処理を遅くしない
        """
        if not isinstance(value, (str, bytes)):
            # 後から書き換えられるもの(リストなど)は、今の内容を残す
            value = format_value(value)
        self._entries.append((time.time(), format_name, value))

    def drain(self) -> str:
        """
        溜まった分を、表示する文字(1件1行)にして取り出す
        """
        lines = []
        # 取り出している間に足された分は、次回に回す(送る側が速くても、終わらなくならないようにする)
        for _ in range(len(self._entries)):
            try:
                lines.append(format_line(*self._entries.popleft()))
            except IndexError:
                break
        return "".join(lines)

    def clear(self) -> None:
        """溜まっている分を、すべて捨てる"""
        self._entries.clear()
