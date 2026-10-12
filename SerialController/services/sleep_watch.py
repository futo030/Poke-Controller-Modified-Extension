#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC がスリープから戻ったことの検知

画面(tkinter)には触れない。PC の設定(スリープ)は、読みも変えもしない。
専用のスレッドが、1 秒ごとに時計を見る。前に見たときからの時間が、1 秒より大きく空いていたら、
その間は PC が止まっていた(スリープ・休止状態)とみなして、渡してある関数を呼ぶ。
(スリープの間は、このスレッドも止まるので、戻ったときに、時計だけが進んでいる)
画面のスレッドが忙しくて止まっていても、このスレッドは動くので、取り違えない。
PC の時計を手で大きく進めた場合は、スリープと同じ扱いになる。
"""
from __future__ import annotations

import threading
import time
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 時計を見る間隔(秒)と、「止まっていた」とみなす空き時間(秒。間隔を除いた分)
CHECK_INTERVAL = 1.0
GAP_THRESHOLD = 20.0


class SleepWatch:
    """PC が止まっていた(スリープから戻った)ことを見つけて、知らせる"""

    def __init__(
        self,
        on_resume: Callable[[float], None],
        interval: float = CHECK_INTERVAL,
        threshold: float = GAP_THRESHOLD,
        clock: Callable[[], float] = time.time,
    ):
        """
        on_resume: 止まっていたことが分かったときに呼ぶ関数(引数は、止まっていた時間(秒)。検知のスレッドから呼ぶ)
        interval: 時計を見る間隔(秒)。threshold: 止まっていたとみなす空き時間(秒)
        clock: 今の時刻(秒)を返す関数(テストで差し替える)
        """
        self._on_resume = on_resume
        self._interval = interval
        self._threshold = threshold
        self._clock = clock
        self._last = None
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        """検知を始める(すでに始めていれば、何もしない)"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._last = self._clock()
        self._thread = threading.Thread(target=self._run, name="SleepWatch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """検知をやめる"""
        self._stop.set()

    def _run(self) -> None:
        """interval 秒ごとに、時計を見る(stop() で終わる)"""
        while not self._stop.wait(self._interval):
            self.check()

    def check(self) -> float:
        """
        時計を見る。前に見たときからの時間が、間隔より threshold 秒を超えて空いていたら、on_resume を呼ぶ。
        戻り値: 止まっていたとみなした時間(秒)。そうでなければ 0
        """
        now = self._clock()
        last, self._last = self._last, now
        if last is None:
            return 0.0
        gap = now - last - self._interval
        if gap <= self._threshold:
            # (時計を戻した場合の、負の値も含む)
            return 0.0
        _logger.info(f"The PC seems to have been suspended for {gap:.0f} seconds")
        try:
            self._on_resume(gap)
        except Exception:
            _logger.exception("Failed to handle the resume from sleep")
        return gap
