#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出力画面(Output)への書き込みの反映
(書き込みの受け渡しは、画面に依存しない services/output_service.py が行う)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import OutputLinks
from Commands.CommandBase import Command
from services.output_service import OutputChannel, OutputService
from ui.constants import (
    OUTPUT_MAX_LINES,
    OUTPUT_FLUSH_INTERVAL_MS,
    ACTION_LINK_TAG,
    ACTION_LINK_TAG_PREFIX,
    CAPTURE_LINK_PREFIX,
    CAPTURE_LINK_TAG,
    LOG_LEVEL_TAGS,
)

if TYPE_CHECKING:
    import tkinter as tk

    from services.serial_monitor import SerialMonitor
    from Window import PokeControllerApp


class OutputTextAreaProxy(object):
    """
    出力画面(Notebook)の各ページにあるTextウィジェットへの呼び出しを振り分けるクラス
    - Startボタンで実行したコマンドのスレッドからの出力: Start時にアクティブだったページ
    - それ以外(GUI操作など)からの出力: 現在アクティブなページ
    """

    def __init__(self, app: PokeControllerApp, text_widgets: list[tk.Text], channel: OutputChannel):
        """
        app: 画面(アクティブなページを調べるのに使う)
        text_widgets: 各ページのTextウィジェットのリスト(ページの順)
        channel: この出力画面(Output#1 または #2)への書き込み口
        """
        self._app = app
        self._text_widgets = text_widgets
        self._channel = channel

    def widget_for_page(self, page: int | None) -> tk.Text:
        """
        指定ページのTextウィジェットを返す(None: アクティブなページ)
        """
        if page is None:
            page = self._app.get_active_output_page()
        return self._text_widgets[page]

    def current_widget(self) -> tk.Text:
        """呼び出したスレッドの出力先のページ(コマンドのスレッド以外は、アクティブなページ)のTextウィジェットを返す"""
        return self.widget_for_page(Command.get_output_page_for_current_thread())

    def enqueue(self, mode: str, text: str = "") -> None:
        """
        出力をキューに積む(任意のスレッドから呼び出し可能、Tkは呼ばない)
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        self._channel.enqueue(mode, text)

    def __getattr__(self, name: str) -> object:
        """このクラスに無い属性やメソッド(insert、configure など)は、出力先のTextウィジェットのものを返す"""
        return getattr(self.current_widget(), name)

    def __setitem__(self, key: str, value: object) -> None:
        """widget["state"] = ... の形の設定を、出力先のTextウィジェットに行う"""
        self.current_widget()[key] = value

    def __getitem__(self, key: str) -> object:
        """widget["state"] の形で、出力先のTextウィジェットの設定の値を返す"""
        return self.current_widget()[key]


class OutputWriter(object):
    """
    出力画面への書き込みを、メインスレッドから反映するクラス
    - 書き込む側は、任意のスレッドから OutputService のキューに積んですぐ戻る
      (別スレッドからTkを呼ぶとメインスレッドの処理完了まで待たされるため、Tkは呼ばない)
    - メインスレッドが after() で定期的にキューを取り出し、Textウィジェット毎にまとめて反映する
    """

    def __init__(
        self,
        root: tk.Misc,
        service: OutputService,
        text_widgets: dict[int, list[tk.Text]],
        get_active_page: Callable[[], int],
        max_lines: int = OUTPUT_MAX_LINES,
        interval_ms: int = OUTPUT_FLUSH_INTERVAL_MS,
    ):
        """
        root: after() で定期的な反映を予約するウィジェット(メインウィンドウ)
        service: 書き込みが溜まっているキューの持ち主
        text_widgets: 出力画面の番号(1 / 2) -> 各ページのTextウィジェットのリスト
        get_active_page: アクティブなページを返す関数
        max_lines: 出力画面に残す行数の上限
        interval_ms: 反映する間隔(ミリ秒)
        """
        self._root = root
        self._service = service
        self._text_widgets = text_widgets
        self._get_active_page = get_active_page
        self._max_lines = max_lines
        self._interval_ms = interval_ms
        self._root.after(self._interval_ms, self._poll)

    def _poll(self) -> None:
        """溜まった出力を反映し、次の反映を予約する(after() から、interval_ms ごとに呼ばれる)"""
        try:
            self.flush()
        finally:
            self._root.after(self._interval_ms, self._poll)

    def flush(self) -> None:
        """
        キューに溜まった出力をまとめて反映する(メインスレッドから呼ぶこと)
        """
        for update in self._service.drain(self._get_active_page):
            self._apply(self._text_widgets[update.area][update.page], update.clear, update.text)

    def _apply(self, widget: tk.Text, clear: bool, text: str) -> None:
        """
        1つのTextウィジェットに、出力を反映する(リンクのタグ付けと、行数の上限を超えた分の削除も行う)
        clear: 書き込む前に、表示中の内容を消すか
        text: 追記する文字(無い場合は空文字)
        """
        try:
            widget.configure(state="normal")
            if clear:
                widget.delete("1.0", "end")
            if text:
                start = widget.index("end-1c")
                if OutputLinks.has_link(text):
                    # クリックで処理を行うリンク: 印を取り除き、リンクの文字にタグを付けて書き込む
                    for part, link_id in OutputLinks.split(text):
                        if link_id is None:
                            widget.insert("end", part)
                        else:
                            widget.insert("end", part, (ACTION_LINK_TAG, f"{ACTION_LINK_TAG_PREFIX}{link_id}"))
                else:
                    widget.insert("end", text)
                if CAPTURE_LINK_PREFIX in text:
                    self._tagCaptureLinks(widget, start)
            last_line = int(widget.index("end-1c").split(".")[0])
            if last_line - 1 > self._max_lines:
                widget.delete("1.0", f"{last_line - self._max_lines}.0")
            widget.configure(state="disabled")
            widget.see("end")
        except Exception:
            # 終了処理中などでウィジェットが破棄されている場合
            pass


    @staticmethod
    def _tagCaptureLinks(widget: tk.Text, start: str) -> None:
        """
        start以降に書き込んだ「capture succeeded: (パス)」の行の、パスの部分をリンクにする
        """
        index = widget.search(CAPTURE_LINK_PREFIX, f"{start} linestart", stopindex="end")
        while index:
            widget.tag_add(CAPTURE_LINK_TAG, f"{index}+{len(CAPTURE_LINK_PREFIX)}c", f"{index} lineend")
            index = widget.search(CAPTURE_LINK_PREFIX, f"{index} lineend", stopindex="end")


class MonitorWriter(object):
    """
    シリアルモニター(Serial タブ)とログ(Log タブ)への書き込みを、メインスレッドから反映するクラス
    - 送る側は、SerialMonitor / LogBuffer に溜めてすぐ戻る(Tkは呼ばない)
    - メインスレッドが after() で定期的に取り出し、溜まった分を1回でまとめて書き込む
      (大量に送っても、書き込みの回数は増えない)
    - is_visible を渡した場合は、表示している間だけ取り出す(見えていない間は、溜めたままにして、画面の処理を増やさない)
    """

    def __init__(
        self,
        root: tk.Misc,
        get_monitor: Callable[[], SerialMonitor | None],
        text_widget: tk.Text,
        max_lines: int = OUTPUT_MAX_LINES,
        interval_ms: int = OUTPUT_FLUSH_INTERVAL_MS,
        is_visible: Callable[[], bool] | None = None,
    ):
        """
        root: after() で定期的な反映を予約するウィジェット(メインウィンドウ)
        get_monitor: SerialMonitor / LogBuffer(drain と clear を持つもの)を返す関数(まだ無い場合は None)
        text_widget: 書き込む先のTextウィジェット
        max_lines: 残す行数の上限
        interval_ms: 反映する間隔(ミリ秒)
        is_visible: 表示しているかを返す関数(None: いつでも反映する)。表示していない間は、取り出さない
        """
        self._is_visible = is_visible
        self._root = root
        self._get_monitor = get_monitor
        self._text_widget = text_widget
        self._max_lines = max_lines
        self._interval_ms = interval_ms
        self._root.after(self._interval_ms, self._poll)

    def _poll(self) -> None:
        """溜まった分を反映し、次の反映を予約する(after() から、interval_ms ごとに呼ばれる)"""
        try:
            self.flush()
        finally:
            self._root.after(self._interval_ms, self._poll)

    def flush(self) -> None:
        """
        溜まった分をまとめて反映する(メインスレッドから呼ぶこと)
        """
        if self._is_visible is not None and not self._is_visible():
            return
        monitor = self._get_monitor()
        text = monitor.drain() if monitor is not None else ""
        if not text:
            return
        widget = self._text_widget
        try:
            widget.configure(state="normal")
            widget.insert("end", text)
            last_line = int(widget.index("end-1c").split(".")[0])
            if last_line - 1 > self._max_lines:
                widget.delete("1.0", f"{last_line - self._max_lines}.0")
            widget.configure(state="disabled")
            widget.see("end")
        except Exception:
            # 終了処理中などでウィジェットが破棄されている場合
            pass

    def clear(self) -> None:
        """
        表示中の内容と、まだ反映していない分を消す(メインスレッドから呼ぶこと)
        """
        monitor = self._get_monitor()
        if monitor is not None:
            monitor.clear()
        self._text_widget.configure(state="normal")
        self._text_widget.delete("1.0", "end")
        self._text_widget.configure(state="disabled")


class LogWriter(MonitorWriter):
    """
    ログ(Log タブ)への書き込みを、メインスレッドから反映するクラス。
    MonitorWriter と同じ動きで、レベルごとに文字の色を変える(色は、タグ LOG_LEVEL_TAGS に付ける)
    """

    def flush(self) -> None:
        """
        溜まった分をまとめて反映する(メインスレッドから呼ぶこと)。
        同じレベルが続く分は 1 つにまとめ、全部を 1 回の書き込みで行う
        """
        if self._is_visible is not None and not self._is_visible():
            return
        monitor = self._get_monitor()
        segments = monitor.drain_segments() if monitor is not None else []
        if not segments:
            return
        # insert(位置, 文字, タグ, 文字, タグ, ...) の形にする
        pieces = []
        for group, text in segments:
            pieces.extend((text, LOG_LEVEL_TAGS.get(group, "")))
        widget = self._text_widget
        try:
            widget.configure(state="normal")
            widget.insert("end", *pieces)
            last_line = int(widget.index("end-1c").split(".")[0])
            if last_line - 1 > self._max_lines:
                widget.delete("1.0", f"{last_line - self._max_lines}.0")
            widget.configure(state="disabled")
            widget.see("end")
        except Exception:
            # 終了処理中などでウィジェットが破棄されている場合
            pass


class StdoutRedirector(object):
    """
    標準出力をtextウィジェットにリダイレクトするクラス
    重いので止めました →# update_idletasks()で出力のたびに随時更新(従来はfor loopのときなどにまとめて出力されることがあった)
    """

    def __init__(self, text_widget: tk.Text | OutputTextAreaProxy):
        """text_widget: 書き込む先(Textウィジェット、または出力画面のプロキシ)"""
        self.text_space = text_widget

    def write(self, string: str) -> None:
        """
        print などから渡された文字を書き込む
        (書き込む先に enqueue があればキューに積み、無ければ、リンクの印を取り除いて直接書き込む)
        """
        text_space = self.text_space
        if hasattr(text_space, "enqueue"):
            text_space.enqueue("a", string)
            return
        text_space.configure(state="normal")
        text_space.insert("end", OutputLinks.strip(string))
        text_space.see("end")
        # text_space.update_idletasks()
        text_space.configure(state="disabled")

    def flush(self) -> None:
        """何もしない(sys.stdout の代わりとして使えるように用意している)"""
        pass
