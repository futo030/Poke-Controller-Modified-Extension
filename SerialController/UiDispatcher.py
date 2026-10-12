#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import queue
import threading
from typing import Any, Callable

# キューを処理する間隔(ms)
DISPATCH_INTERVAL_MS = 16


class UiDispatcher:
    """
    GUI(Tk)の操作をメインスレッドで実行するためのクラス
    - 別スレッドからTkを呼ぶと、メインスレッドの処理完了まで呼び出し元が待たされる
      (メインスレッドが忙しいほど待ちが長くなる)
    - 別スレッドからは関数をキューに積み、メインスレッドが after() で定期的に取り出して実行する
    - メインスレッドからの呼び出しはその場で実行する
    """

    _root = None
    _queue = queue.SimpleQueue()
    _running = False
    _interval_ms = DISPATCH_INTERVAL_MS

    @classmethod
    def init(cls, root: Any, interval_ms: int = DISPATCH_INTERVAL_MS) -> None:
        """
        メインスレッドから1回だけ呼ぶ
        root: tkinter のルートウィンドウ(tk.Tk。このファイルは tkinter を読み込まないので、型は Any にしている)
        interval_ms: キューを処理する間隔(ミリ秒)
        """
        cls._root = root
        cls._interval_ms = interval_ms
        cls._running = True
        root.bind("<Destroy>", cls._on_destroy, add="+")
        root.after(cls._interval_ms, cls._poll)

    @staticmethod
    def is_main_thread() -> bool:
        """今のスレッドが、メインスレッドか"""
        return threading.current_thread() is threading.main_thread()

    @classmethod
    def post(cls, func: Callable, *args: Any, **kwargs: Any) -> None:
        """
        メインスレッドで func を実行する(結果を待たずにすぐ戻る)
        args / kwargs: func に渡す引数。メインスレッドから呼んだ場合と、init の前・画面を閉じた後は、その場で実行する
        """
        if cls.is_main_thread() or not cls._running:
            func(*args, **kwargs)
            return
        cls._queue.put((func, args, kwargs, None))

    @classmethod
    def call(cls, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        メインスレッドで func を実行し、その戻り値を返す(例外はそのまま送出する)
        呼び出し元スレッドはTkではなくEventで待つ
        待っている間に画面が閉じた場合は RuntimeError
        """
        if cls.is_main_thread() or not cls._running:
            return func(*args, **kwargs)
        result = _CallResult()
        cls._queue.put((func, args, kwargs, result))
        while not result.event.wait(0.1):
            if not cls._running:
                raise RuntimeError("GUI has been closed.")
        if result.error is not None:
            raise result.error
        return result.value

    @classmethod
    def _poll(cls) -> None:
        """キューを処理して、次の処理を予約する(after で、定期的に呼ばれる)"""
        try:
            cls.flush()
        finally:
            if cls._running:
                cls._root.after(cls._interval_ms, cls._poll)

    @classmethod
    def flush(cls) -> None:
        """
        キューに溜まった関数を実行する(メインスレッドから呼ぶこと)
        """
        # 実行中に積まれた分は次回に回す(ダイアログ等で入れ子になっても無限に回らないように)
        for _ in range(cls._queue.qsize()):
            try:
                func, args, kwargs, result = cls._queue.get_nowait()
            except queue.Empty:
                break
            try:
                value = func(*args, **kwargs)
                if result is not None:
                    result.value = value
            except BaseException as e:
                if result is not None:
                    result.error = e
                else:
                    import traceback

                    traceback.print_exc()
            finally:
                if result is not None:
                    result.event.set()

    @classmethod
    def _on_destroy(cls, event: Any) -> None:
        """ルートウィンドウが閉じたときに、処理を止め、結果を待っているスレッドを解放する(event: tkinter のイベント)"""
        if event.widget is cls._root:
            cls._running = False
            # 待っているスレッドを解放する
            while True:
                try:
                    _, _, _, result = cls._queue.get_nowait()
                except queue.Empty:
                    break
                if result is not None:
                    result.error = RuntimeError("GUI has been closed.")
                    result.event.set()


class _CallResult(object):
    """call() の結果の受け渡し(終わったことの合図、戻り値、例外)"""

    def __init__(self):
        """まだ終わっていない状態で作る"""
        self.event = threading.Event()
        self.value = None
        self.error = None
