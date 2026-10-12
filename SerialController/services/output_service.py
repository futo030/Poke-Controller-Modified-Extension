#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出力画面(Output#1 / #2)への書き込みの受け渡し

画面(tkinter)には触れない。
- 書き込む側(コマンドのスレッドなど)は、enqueue() でキューに積んですぐ戻る
- 表示する側(画面)は、drain() で溜まった分をまとめて受け取り、自分のスレッドで反映する
"""
from __future__ import annotations

import queue
import sys
from typing import Callable, NamedTuple

# 出力画面の番号(Output#1 / #2)
AREAS = (1, 2)
DEFAULT_MAX_LINES = 10000


class OutputUpdate(NamedTuple):
    """
    1つの出力画面に反映する内容
    """

    area: int  # 出力画面の番号(1 / 2)
    page: int  # ページ(0始まり)
    clear: bool  # 書き込む前に、表示中の内容を消すか
    text: str  # 追記する文字(無い場合は空文字)


class OutputChannel:
    """
    1つの出力画面(Output#1 または #2)への書き込み口
    """

    def __init__(self, service: OutputService, area: int):
        """service: 書き込みを受け取る OutputService、area: 出力画面の番号(1 / 2)"""
        self._service = service
        self.area = area

    def enqueue(self, mode: str, text: str = "") -> None:
        """
        出力をキューに積む(任意のスレッドから呼び出し可能)
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        self._service.enqueue(self.area, mode, text)


class StdoutWriter:
    """
    標準出力(print)を、出力画面に送る
    """

    def __init__(self, channel: OutputChannel):
        """channel: 書き込み先の出力画面"""
        self.channel = channel

    def write(self, string: str) -> None:
        """文字を、出力画面に追記する(sys.stdout の write の代わり)"""
        self.channel.enqueue("a", string)

    def flush(self) -> None:
        """何もしない(sys.stdout の代わりにするために要る)"""
        pass


class OutputService:
    """出力画面への書き込みをキューに溜め、表示する側に、まとめて渡す"""

    def __init__(self, get_page: Callable[[], int | None] | None = None, max_lines: int = DEFAULT_MAX_LINES):
        """
        get_page: 書き込むスレッドの出力先のページを返す関数(None: 反映する時点で表示中のページ)
        max_lines: 出力画面に残す行数の上限
        """
        self._get_page = get_page if get_page is not None else (lambda: None)
        self._max_lines = max_lines
        self._queue = queue.SimpleQueue()
        # 書き込みのたびに呼ぶ関数(出力画面の番号, mode, 文字)。書き込んだスレッドで呼ぶので、待たせない処理だけを登録する
        self.listeners: list[Callable[[int, str, str], None]] = []
        self._channels = {area: OutputChannel(self, area) for area in AREAS}

    def channel(self, area: int) -> OutputChannel:
        """その番号(1 / 2)の出力画面への書き込み口を返す(番号が違う場合は KeyError)"""
        return self._channels[int(area)]

    def enqueue(self, area: int, mode: str, text: str = "") -> None:
        """
        出力をキューに積む(任意のスレッドから呼び出し可能)
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        # 出力先ページは呼び出し元スレッドで確定させる(Noneは反映時に表示中のページ)
        self._queue.put((area, self._get_page(), mode, text))
        for listener in self.listeners:
            listener(area, mode, text)

    def redirect_stdout(self, area: int) -> None:
        """
        標準出力(print)の出力先を、その出力画面にする
        """
        sys.stdout = StdoutWriter(self.channel(area))

    def drain(self, get_active_page: Callable[[], int]) -> list[OutputUpdate]:
        """
        キューに溜まった出力を、出力画面・ページごとにまとめて取り出す。
        get_active_page: 表示中のページを返す関数(ページが決まっていない出力がある場合のみ呼ぶ)
        """
        # 出力画面・ページごとに [削除の有無, 追記する文字列のリスト] にまとめる
        pending = {}
        while True:
            try:
                area, page, mode, text = self._queue.get_nowait()
            except queue.Empty:
                break
            if page is None:
                page = get_active_page()
            entry = pending.setdefault((area, page), [False, []])
            if mode in ["w", "d"]:
                # それ以前の内容は全て消えるので、溜めていた追記も破棄する
                entry[0] = True
                entry[1] = []
            if mode in ["w", "a"]:
                entry[1].append(text)
        updates = []
        for (area, page), (clear, chunks) in pending.items():
            text = "".join(chunks)
            # 今回分だけで上限を超える場合、既存の内容は全て消えるので末尾のみ残す
            if text.count("\n") > self._max_lines:
                text = "\n".join(text.split("\n")[-(self._max_lines + 1):])
                clear = True
            updates.append(OutputUpdate(area, page, clear, text))
        return updates
