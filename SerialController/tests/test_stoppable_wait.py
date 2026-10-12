#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
待機(wait / short_wait / press などの待ち)を、途中で止められるようにした変更のテスト(画面を起動せずに実行できる)

- 止める指示がないときは、これまでの待機(待ってから、止める指示を確かめる)と、時刻も、送る順番も同じ
- 長い待機の途中で止める指示が出たら、待ち終わる前に終了する

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Commands import PythonCommandBase  # noqa: E402
from Commands.Keys import Button  # noqa: E402
from Commands.PythonCommandBase import PythonCommand, StopThread  # noqa: E402


def setUpModule():
    """通知のクラスを代役にする(コマンドを作るたびに、本物の通知先へ接続を確かめに行かないようにする)"""
    for name in ("Line_Notify", "Discord_Notify"):
        patcher = mock.patch(f"Commands.PythonCommandBase.{name}")
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)

class FakeClock:
    """進めた分だけ進む時計(sleep と、終わり際の合わせ込みの代わり)"""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def perf_counter(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def precise_sleep(self, duration):
        # 本物と同じく、0 以下・数でない値(nan)は待たない(本物は、時計が自分で進まないと終わらないので、差し替える)
        if duration > 0:
            self.now += duration


class FakeKeys:
    """送る代わりに、呼ばれた順番と時刻を記録する"""

    def __init__(self, clock):
        self.clock = clock
        self.log = []

    def _add(self, name, value=None):
        self.log.append((name, value, round(self.clock.perf_counter() - 1000.0, 9)))

    def input(self, value):
        self._add("input", value)

    def inputEnd(self, value):
        self._add("inputEnd", value)

    def hold(self, value):
        self._add("hold", value)

    def holdEnd(self, value):
        self._add("holdEnd", value)

    def end(self):
        self._add("end")


class LegacyCommand(PythonCommand):
    """これまでの待機(待ってから、止める指示を確かめる)に戻したコマンド"""

    def _sleepStoppable(self, wait):
        PythonCommandBase.precise_sleep(float(wait))
        self.checkIfAlive()


def script(command):
    """短い待ちと長い待ちを混ぜた、入力の並び"""
    command.press(Button.A, 0.1, 0.5)
    command.wait(0.05)
    command.press(Button.B, duration=1.0, wait=0.2)
    command.hold(Button.X, wait=3.0)
    command.short_wait(0.25)
    command.holdEnd(Button.X)
    command.pressRep(Button.A, 3, duration=0.1, interval=0.3, wait=2.0)
    command.wait(0)
    command.wait("0.75")
    command.wait(10)


class WithFakeClock(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        for target, name, value in (
            (PythonCommandBase.time, "perf_counter", self.clock.perf_counter),
            (PythonCommandBase, "sleep", self.clock.sleep),
            (PythonCommandBase, "precise_sleep", self.clock.precise_sleep),
        ):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        saved = PythonCommand.isPause
        PythonCommand.isPause = False
        self.addCleanup(lambda: setattr(PythonCommand, "isPause", saved))

    def command(self, cls=PythonCommand):
        command = cls()
        command.keys = FakeKeys(self.clock)
        command.alive = True
        command.postProcess = None
        return command

    def elapsed(self):
        return round(self.clock.now - 1000.0, 9)


class SameAsBeforeTest(WithFakeClock):
    def test_script_sends_the_same_things_at_the_same_times(self):
        legacy = self.command(LegacyCommand)
        script(legacy)
        legacy_end = self.elapsed()
        self.clock.now = 1000.0
        current = self.command()
        script(current)
        self.assertEqual(current.keys.log, legacy.keys.log)
        self.assertEqual(self.elapsed(), legacy_end)
        self.assertGreater(len(legacy.keys.log), 10)

    def test_each_wait_ends_at_the_same_time(self):
        for seconds in (0, 0.001, 0.016, 0.1, 0.2, 0.2000001, 0.25, 0.3, 0.999, 1, 2.5, 30, 3600):
            with self.subTest(seconds=seconds):
                self.clock.now = 1000.0
                self.command(LegacyCommand).wait(seconds)
                expected = self.elapsed()
                self.clock.now = 1000.0
                self.command().wait(seconds)
                self.assertEqual(self.elapsed(), expected)

    def test_short_wait_is_one_sleep_as_before(self):
        # 区切る間隔の 2 倍以下は、途中で確かめない(これまでと同じ 1 回の待ち)
        for seconds in (0.001, 0.05, 0.1, 0.2):
            with self.subTest(seconds=seconds), mock.patch.object(PythonCommandBase, "precise_sleep") as precise:
                self.clock.sleeps.clear()
                self.command().wait(seconds)
                precise.assert_called_once_with(seconds)
                self.assertEqual(self.clock.sleeps, [])

    def test_long_wait_is_split_and_the_end_is_adjusted_precisely(self):
        with mock.patch.object(PythonCommandBase, "precise_sleep") as precise:
            self.command().wait(1.0)
        # 0.1 秒ずつ 8 回待ち、残り(0.2 秒)は、これまでと同じ関数で終わりを合わせる
        self.assertEqual(self.clock.sleeps, [0.1] * 8)
        self.assertAlmostEqual(precise.call_args[0][0], 0.2, places=9)

    def test_odd_values_behave_as_before(self):
        for value in (-1, -0.5, float("nan"), "0.01", True):
            with self.subTest(value=value):
                self.clock.now = 1000.0
                self.command(LegacyCommand).wait(value)
                expected = self.elapsed()
                self.clock.now = 1000.0
                self.command().wait(value)
                self.assertEqual(self.elapsed(), expected)
        for value in (None, "abc", [1]):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)) as legacy:
                    self.command(LegacyCommand).wait(value)
                with self.assertRaises(type(legacy.exception)):
                    self.command().wait(value)

    def test_stop_requested_before_a_short_wait_stops_after_it(self):
        # 短い待ちは、これまでどおり、待ち終わってから止まる
        for cls in (LegacyCommand, PythonCommand):
            with self.subTest(cls=cls.__name__):
                self.clock.now = 1000.0
                command = self.command(cls)
                keys = command.keys
                command.alive = False
                with self.assertRaises(StopThread):
                    command.wait(0.15)
                self.assertEqual(self.elapsed(), 0.15)
                self.assertEqual(keys.log, [("end", None, 0.15)])


class StopInTheMiddleTest(WithFakeClock):
    def stop_after(self, command, seconds):
        """時計が seconds 進んだ所で、止める指示を出す"""
        original = self.clock.sleep

        def sleep(amount):
            original(amount)
            if self.elapsed() >= seconds:
                command.alive = False

        patcher = mock.patch.object(PythonCommandBase, "sleep", sleep)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_long_wait_stops_at_the_next_check(self):
        command = self.command()
        keys = command.keys
        self.stop_after(command, 0.3)
        with self.assertRaises(StopThread):
            command.wait(30)
        self.assertAlmostEqual(self.elapsed(), 0.3, places=6)
        # 止まるときの処理は、これまでと同じ(入力を離す、keys と thread を手放す)
        self.assertEqual([entry[0] for entry in keys.log], ["end"])
        self.assertIsNone(command.keys)
        self.assertIsNone(command.thread)

    def test_legacy_wait_stopped_only_at_the_end(self):
        # (比較のため)これまでの待機は、止める指示が出ていても、待ち終わるまで止まらなかった
        command = self.command(LegacyCommand)
        command.alive = False
        with self.assertRaises(StopThread):
            command.wait(30)
        self.assertAlmostEqual(self.elapsed(), 30, places=6)

    def test_long_press_is_released_when_stopped(self):
        command = self.command()
        keys = command.keys
        self.stop_after(command, 0.5)
        with self.assertRaises(StopThread):
            command.press(Button.A, duration=10, wait=1)
        # 押したまま止めると、これまでと同じく、end() が入力を離す(inputEnd は呼ばれない)
        self.assertEqual([entry[0] for entry in keys.log], ["input", "end"])
        self.assertAlmostEqual(keys.log[-1][2], 0.5, places=6)

    def test_post_process_is_requested_once(self):
        command = self.command()
        calls = []
        command.postProcess = lambda: calls.append("post")
        self.stop_after(command, 0.2)
        with mock.patch.object(PythonCommandBase.UiDispatcher, "post", lambda function: function()):
            with self.assertRaises(StopThread):
                command.wait(5)
        self.assertEqual(calls, ["post"])
        self.assertIsNone(command.postProcess)


class RealTimeTest(unittest.TestCase):
    """実際の時計で動かす(時間の許す幅は、広く取る)"""

    def command(self):
        command = PythonCommand()
        command.keys = FakeKeys(time)
        command.alive = True
        command.postProcess = None
        return command

    def test_stop_ends_a_long_wait_soon(self):
        command = self.command()
        result = {}

        def run():
            started = time.perf_counter()
            try:
                command.wait(30)
                result["end"] = "finished"
            except StopThread:
                result["end"] = "stopped"
            result["seconds"] = time.perf_counter() - started

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        time.sleep(0.35)
        command.alive = False
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["end"], "stopped")
        self.assertLess(result["seconds"], 1.0)

    def test_wait_takes_the_requested_time(self):
        command = self.command()
        for seconds in (0.05, 0.3, 0.55):
            with self.subTest(seconds=seconds):
                best = min(self.measure(command, seconds) for _ in range(3))
                self.assertGreaterEqual(best, seconds)
                self.assertLess(best - seconds, 0.02)

    @staticmethod
    def measure(command, seconds):
        started = time.perf_counter()
        command.wait(seconds)
        return time.perf_counter() - started


if __name__ == "__main__":
    unittest.main()
