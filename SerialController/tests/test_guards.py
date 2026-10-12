#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
実行中のコマンドを守る仕組みのテスト(画面を起動せずに実行できる)
- services/sleep_watch.py: PC がスリープから戻ったことの検知
- Commands/Sender.py: 送信の失敗が続いたことの知らせ
- services/app_core.py: それらを受けて、実行中のコマンドを止める

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import inspect
import io
import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import serial

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Commands import Sender as sender_module  # noqa: E402
from Commands.Sender import SEND_FAILURE_LIMIT, Sender  # noqa: E402
from services import app_core, command_service, sleep_watch  # noqa: E402
from services.app_core import AppCore  # noqa: E402
from services.sleep_watch import SleepWatch  # noqa: E402


class SleepWatchTest(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.resumed = []
        self.watch = SleepWatch(self.resumed.append, interval=1.0, threshold=20.0, clock=lambda: self.now)

    def tick(self, seconds):
        self.now += seconds
        return self.watch.check()

    def test_normal_ticks_are_not_a_sleep(self):
        self.watch.check()
        for seconds in (1.0, 1.02, 0.98, 3.0, 20.9):
            self.assertEqual(self.tick(seconds), 0.0)
        self.assertEqual(self.resumed, [])

    def test_a_long_gap_is_a_sleep(self):
        self.watch.check()
        self.tick(1.0)
        gap = self.tick(3601.0)
        self.assertEqual(gap, 3600.0)
        self.assertEqual(self.resumed, [3600.0])
        # その後は、ふつうに戻る(同じスリープを、2 回知らせない)
        self.tick(1.0)
        self.assertEqual(self.resumed, [3600.0])

    def test_the_first_check_and_a_clock_set_back_are_ignored(self):
        self.assertEqual(self.watch.check(), 0.0)
        self.assertEqual(self.tick(-500.0), 0.0)
        self.assertEqual(self.tick(1.0), 0.0)
        self.assertEqual(self.resumed, [])

    def test_an_error_in_the_handler_does_not_stop_the_watch(self):
        def broken(seconds):
            raise RuntimeError("boom")

        watch = SleepWatch(broken, clock=lambda: self.now)
        watch.check()
        self.now += 100
        with self.assertLogs(sleep_watch._logger, "ERROR"):
            self.assertEqual(watch.check(), 99.0)

    def test_the_thread_checks_by_itself_and_stops(self):
        # 本物のスレッドで動かす(時計は差し替えて、1 回だけ大きく進める)
        times = iter([0.0, 0.05, 500.0])
        last = [500.0]

        def clock():
            last[0] = next(times, last[0] + 0.05)
            return last[0]

        watch = SleepWatch(self.resumed.append, interval=0.05, threshold=20.0, clock=clock)
        watch.start()
        watch.start()
        deadline = time.time() + 5
        while not self.resumed and time.time() < deadline:
            time.sleep(0.01)
        watch.stop()
        self.assertEqual(len(self.resumed), 1)
        self.assertGreater(self.resumed[0], 400)
        watch._thread.join(2)
        self.assertFalse(watch._thread.is_alive())
        self.assertTrue(watch._thread.daemon)

    def test_the_sleep_setting_of_the_pc_is_not_touched(self):
        source = inspect.getsource(sleep_watch)
        self.assertNotIn("SetThreadExecutionState", source)
        self.assertNotIn("ctypes", source)


class FlakySerial:
    """決めた回数だけ、書き込みに失敗するシリアルポートの代役"""

    def __init__(self):
        self.fail = 0
        self.written = []

    def write(self, data):
        if self.fail > 0:
            self.fail -= 1
            raise serial.serialutil.SerialException("WriteFile failed")
        self.written.append(data)


class SendFailureTest(unittest.TestCase):
    def setUp(self):
        self.sender = Sender(False)
        self.port = FlakySerial()
        self.sender.ser = self.port
        self.reported = []
        self.sender.on_send_failures = lambda count, error: self.reported.append((count, str(error)))

    def write(self, count=1):
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(count):
                self.sender.writeRow("0x0004 8")

    def test_successes_report_nothing(self):
        self.write(20)
        self.assertEqual(self.reported, [])
        self.assertEqual(len(self.port.written), 20)

    def test_failures_in_a_row_are_reported_once(self):
        self.port.fail = 100
        self.write(SEND_FAILURE_LIMIT - 1)
        self.assertEqual(self.reported, [])
        self.write(1)
        self.assertEqual(self.reported, [(SEND_FAILURE_LIMIT, "WriteFile failed")])
        # 続いている間は、もう知らせない
        self.write(30)
        self.assertEqual(len(self.reported), 1)

    def test_a_success_resets_the_count(self):
        self.port.fail = SEND_FAILURE_LIMIT - 1
        self.write(SEND_FAILURE_LIMIT - 1)
        self.write(1)
        self.port.fail = SEND_FAILURE_LIMIT - 1
        self.write(SEND_FAILURE_LIMIT - 1)
        self.assertEqual(self.reported, [])

    def test_failures_are_reported_again_after_a_success(self):
        self.port.fail = SEND_FAILURE_LIMIT
        self.write(SEND_FAILURE_LIMIT)
        self.write(1)
        self.port.fail = SEND_FAILURE_LIMIT
        self.write(SEND_FAILURE_LIMIT)
        self.assertEqual(len(self.reported), 2)

    def test_a_port_that_was_never_opened_is_not_a_failure(self):
        # 接続せずにスクリプトを試す場合(ポートを開いていない)は、止めない
        self.sender.ser = None
        self.write(SEND_FAILURE_LIMIT * 3)
        self.assertEqual(self.reported, [])

    def test_bytes_and_the_other_row_writer_are_counted_too(self):
        self.port.fail = 100
        with contextlib.redirect_stdout(io.StringIO()), self.sender._lock if hasattr(self.sender, "_lock") else contextlib.nullcontext():
            for _ in range(2):
                self.sender._writeList(b"\x01\x02")
            for _ in range(SEND_FAILURE_LIMIT - 2):
                self.sender._writeRow_wo_perf_counter("end")
        self.assertEqual(len(self.reported), 1)

    def test_no_handler_and_a_broken_handler_do_not_break_sending(self):
        self.sender.on_send_failures = None
        self.port.fail = SEND_FAILURE_LIMIT
        self.write(SEND_FAILURE_LIMIT + 1)
        self.assertEqual(len(self.port.written), 1)

        def broken(count, error):
            raise RuntimeError("boom")

        self.sender.on_send_failures = broken
        self.port.fail = SEND_FAILURE_LIMIT
        with self.assertLogs(sender_module.__name__, "ERROR"):
            self.write(SEND_FAILURE_LIMIT)
        self.write(1)
        self.assertEqual(len(self.port.written), 2)

    def test_the_limit_is_small_enough_to_stop_soon(self):
        self.assertTrue(2 <= SEND_FAILURE_LIMIT <= 10)


class CoreGuardTest(unittest.TestCase):
    """AppCore(Web ブラウザ版の本体)が、知らせを受けて、実行中のコマンドを止める"""

    def setUp(self):
        self.stopped = []
        self.core = SimpleNamespace(
            commands=SimpleNamespace(state=command_service.RUNNING), stop_command=lambda: self.stopped.append(1)
        )
        self.printed = io.StringIO()

    def call(self, method, *args):
        with contextlib.redirect_stdout(self.printed):
            getattr(AppCore, method)(self.core, *args)

    def test_send_failures_stop_the_running_command(self):
        self.call("_on_send_failures", 5, OSError("WriteFile failed"))
        self.assertEqual(self.stopped, [1])
        text = self.printed.getvalue()
        self.assertIn("送信に 5 回続けて失敗しました", text)
        self.assertIn("WriteFile failed", text)
        self.assertIn("実行中のコマンドを止めます", text)

    def test_send_failures_while_idle_only_tell(self):
        self.core.commands.state = command_service.IDLE
        self.call("_on_send_failures", 5, OSError("x"))
        self.assertEqual(self.stopped, [])
        self.assertIn("送信に 5 回続けて失敗しました", self.printed.getvalue())
        self.assertNotIn("止めます", self.printed.getvalue())

    def test_resume_from_sleep_stops_the_running_command(self):
        self.call("_on_resume_from_sleep", 3725.0)
        self.assertEqual(self.stopped, [1])
        self.assertIn("約 1 時間 02 分 05 秒、止まっていました", self.printed.getvalue())

    def test_resume_from_sleep_while_idle_or_stopping_does_nothing(self):
        for state in (command_service.IDLE, command_service.STOPPING):
            self.core.commands.state = state
            self.call("_on_resume_from_sleep", 100.0)
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.printed.getvalue(), "")

    def test_the_core_connects_the_sender_and_the_watch(self):
        source = inspect.getsource(app_core.AppCore.__init__)
        self.assertIn("self.sender.on_send_failures = self._on_send_failures", source)
        self.assertIn("SleepWatch(self._on_resume_from_sleep)", source)
        self.assertIn("self.sleep_watch.start()", inspect.getsource(app_core.AppCore.start))
        self.assertIn("self.sleep_watch.stop()", inspect.getsource(app_core.AppCore.close))


class ThreadSafetyTest(unittest.TestCase):
    def test_failures_from_several_threads_are_reported_once(self):
        sender = Sender(False)
        port = FlakySerial()
        port.fail = 10 ** 6
        sender.ser = port
        reported = []
        sender.on_send_failures = lambda count, error: reported.append(count)

        def work():
            with contextlib.redirect_stdout(io.StringIO()):
                for _ in range(50):
                    sender.writeRow("x")

        threads = [threading.Thread(target=work) for _ in range(4)]
        with mock.patch.object(sender_module, "SEND_FAILURE_LIMIT", 5):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len(reported), 1)


if __name__ == "__main__":
    unittest.main()
