#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/run_schedule.py(コマンドの開始と停止の予約)のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import run_schedule  # noqa: E402
from services.run_schedule import RunSchedule  # noqa: E402

START = datetime.datetime(2026, 10, 11, 22, 0, 0)


class ScheduleCase(unittest.TestCase):
    def setUp(self):
        self.now = START
        self.running = False
        self.can_start = True
        self.started = []
        self.stopped = 0
        self.messages = []
        self.schedule = RunSchedule(
            self.start, self.stop, lambda: self.running, self.messages.append, now=lambda: self.now
        )

    def start(self, command_type, name):
        self.started.append((command_type, name))
        if self.can_start:
            self.running = True
        return self.can_start

    def stop(self):
        self.stopped += 1
        self.running = False

    def advance(self, **delta):
        self.now += datetime.timedelta(**delta)
        self.schedule.tick()


class StartTest(ScheduleCase):
    def test_command_starts_at_the_time(self):
        self.schedule.reserve_start(START + datetime.timedelta(minutes=30), "Python", "A連打")
        self.assertTrue(self.schedule.pending)
        self.advance(minutes=29, seconds=59)
        self.assertEqual(self.started, [])
        self.advance(seconds=1)
        self.assertEqual(self.started, [("Python", "A連打")])
        self.assertFalse(self.schedule.pending)
        # 1 回だけ
        self.advance(minutes=10)
        self.assertEqual(len(self.started), 1)

    def test_start_is_skipped_while_another_command_is_running(self):
        self.schedule.reserve_start(START + datetime.timedelta(minutes=1), "Python", "A連打")
        self.running = True
        self.advance(minutes=1)
        self.assertEqual(self.started, [])
        self.assertFalse(self.schedule.pending)
        self.assertTrue(any("実行中のため" in message for message in self.messages))

    def test_failure_to_start_is_reported(self):
        self.can_start = False
        self.schedule.reserve_start(START + datetime.timedelta(minutes=1), "Python", "消したコマンド")
        self.advance(minutes=1)
        self.assertTrue(any("開始できませんでした" in message for message in self.messages))

    def test_cancel_and_replace(self):
        self.schedule.reserve_start(START + datetime.timedelta(minutes=1), "Python", "a")
        self.schedule.reserve_start(START + datetime.timedelta(minutes=5), "Mcu", "b")
        self.advance(minutes=2)
        self.assertEqual(self.started, [])
        self.schedule.cancel_start()
        self.advance(minutes=10)
        self.assertEqual(self.started, [])
        self.assertFalse(self.schedule.pending)


class StopTest(ScheduleCase):
    def test_stop_at_a_time(self):
        self.running = True
        self.schedule.reserve_stop_at(START + datetime.timedelta(minutes=10))
        self.advance(minutes=9)
        self.assertEqual(self.stopped, 0)
        self.advance(minutes=1)
        self.assertEqual(self.stopped, 1)
        self.assertFalse(self.schedule.pending)

    def test_stop_after_minutes_counts_from_now_while_running(self):
        self.running = True
        self.assertEqual(self.schedule.reserve_stop_after(5), "")
        self.assertEqual(self.schedule.stop_at, START + datetime.timedelta(minutes=5))
        self.advance(minutes=5)
        self.assertEqual(self.stopped, 1)

    def test_stop_after_minutes_counts_from_the_reserved_start(self):
        self.schedule.reserve_start(START + datetime.timedelta(minutes=30), "Python", "a")
        self.assertEqual(self.schedule.reserve_stop_after(20), "")
        self.assertIsNone(self.schedule.stop_at)
        self.advance(minutes=30)
        self.assertEqual(self.started, [("Python", "a")])
        self.assertEqual(self.schedule.stop_at, START + datetime.timedelta(minutes=50))
        self.advance(minutes=19)
        self.assertEqual(self.stopped, 0)
        self.advance(minutes=1)
        self.assertEqual(self.stopped, 1)
        self.assertFalse(self.schedule.pending)

    def test_stop_after_needs_a_running_command_or_a_reserved_start(self):
        self.assertIn("実行中か", self.schedule.reserve_stop_after(5))
        self.assertFalse(self.schedule.pending)

    def test_stop_after_is_cancelled_when_the_start_fails_or_is_cancelled(self):
        self.can_start = False
        self.schedule.reserve_start(START + datetime.timedelta(minutes=1), "Python", "a")
        self.schedule.reserve_stop_after(5)
        self.advance(minutes=1)
        self.assertFalse(self.schedule.pending)
        self.schedule.reserve_start(START + datetime.timedelta(minutes=10), "Python", "a")
        self.schedule.reserve_stop_after(5)
        self.schedule.cancel_start()
        self.assertFalse(self.schedule.pending)

    def test_stop_is_dropped_when_the_command_ends_first(self):
        self.running = True
        self.schedule.reserve_stop_at(START + datetime.timedelta(minutes=10))
        self.advance(minutes=1)
        self.running = False
        self.advance(minutes=1)
        self.assertFalse(self.schedule.pending)
        self.assertTrue(any("コマンドが終わったので" in message for message in self.messages))
        self.advance(minutes=20)
        self.assertEqual(self.stopped, 0)

    def test_stop_reserved_while_idle_waits_for_a_command(self):
        # 実行していないときに予約した「時刻で停止」は、その後に始まったコマンドを止める
        self.schedule.reserve_stop_at(START + datetime.timedelta(minutes=10))
        self.advance(minutes=1)
        self.assertTrue(self.schedule.pending)
        self.running = True
        self.advance(minutes=9)
        self.assertEqual(self.stopped, 1)

    def test_stop_time_with_nothing_running(self):
        self.schedule.reserve_stop_at(START + datetime.timedelta(minutes=1))
        self.advance(minutes=1)
        self.assertEqual(self.stopped, 0)
        self.assertFalse(self.schedule.pending)
        self.assertTrue(any("実行中のコマンドはありませんでした" in message for message in self.messages))

    def test_cancel_stop(self):
        self.running = True
        self.schedule.reserve_stop_at(START + datetime.timedelta(minutes=1))
        self.schedule.cancel_stop()
        self.advance(minutes=5)
        self.assertEqual(self.stopped, 0)


class SleepTest(ScheduleCase):
    """PC の設定(スリープ)は変えない。スリープしていた場合に、遅れて始めない"""

    def test_the_sleep_setting_of_the_pc_is_not_touched(self):
        import inspect

        source = inspect.getsource(run_schedule)
        self.assertNotIn("SetThreadExecutionState", source)
        self.assertNotIn("ctypes", source)
        self.assertFalse(hasattr(run_schedule, "keep_awake"))
        self.assertIn("スリープ", run_schedule.SLEEP_WARNING)
        self.assertIn("正常に動作しません", run_schedule.SLEEP_WARNING)

    def test_start_is_skipped_when_the_time_passed_long_ago(self):
        # PC がスリープしていて、2 時間後に戻った場合
        self.schedule.reserve_start(START + datetime.timedelta(minutes=30), "Python", "A連打")
        self.schedule.reserve_stop_after(20)
        self.advance(hours=2, minutes=30)
        self.assertEqual(self.started, [])
        self.assertFalse(self.schedule.pending)
        self.assertTrue(any("過ぎていたので" in m and "スリープ" in m for m in self.messages), self.messages)
        self.assertTrue(any("「開始から」の停止の予約を取り消しました" in m for m in self.messages))

    def test_start_a_little_late_still_starts(self):
        self.schedule.reserve_start(START + datetime.timedelta(minutes=30), "Python", "A連打")
        self.advance(minutes=30, seconds=run_schedule.START_LATE_LIMIT_SECONDS)
        self.assertEqual(self.started, [("Python", "A連打")])

    def test_stop_still_works_after_the_time_passed(self):
        # 停止は、遅れても行う(止めない方が困るため)
        self.running = True
        self.schedule.reserve_stop_at(START + datetime.timedelta(minutes=10))
        self.advance(hours=3)
        self.assertEqual(self.stopped, 1)

    def test_cancel_all(self):
        self.schedule.reserve_start(START + datetime.timedelta(minutes=1), "Python", "a")
        self.schedule.reserve_stop_after(5)
        self.schedule.cancel_all()
        self.assertFalse(self.schedule.pending)
        self.assertEqual(self.messages[-1].startswith("停止を予約しました"), True)
        self.advance(minutes=10)
        self.assertEqual(self.started, [])


class TextTest(ScheduleCase):
    def test_clock_means_the_next_time_it_comes(self):
        self.assertEqual(run_schedule.parse_clock("23:30", START), datetime.datetime(2026, 10, 11, 23, 30))
        self.assertEqual(run_schedule.parse_clock(" 6:05 ", START), datetime.datetime(2026, 10, 12, 6, 5))
        self.assertEqual(run_schedule.parse_clock("22:00", START), datetime.datetime(2026, 10, 12, 22, 0))
        self.assertEqual(run_schedule.parse_clock("22:00:30", START), datetime.datetime(2026, 10, 11, 22, 0, 30))
        self.assertEqual(run_schedule.parse_clock("23：15", START), datetime.datetime(2026, 10, 11, 23, 15))

    def test_bad_clocks(self):
        for text in ("", "2330", "24:00", "12:60", "a:b", "1:2:3:4", "-1:00"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                run_schedule.parse_clock(text, START)

    def test_minutes(self):
        self.assertEqual(run_schedule.parse_minutes(" 1.5 "), 1.5)
        for text in ("", "abc", "0", "-3", "nan", "100000"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                run_schedule.parse_minutes(text)

    def test_remaining_time(self):
        self.assertEqual(run_schedule.format_remaining(3723), "1 時間 02 分 03 秒")
        self.assertEqual(run_schedule.format_remaining(65.2), "1 分 06 秒")
        self.assertEqual(run_schedule.format_remaining(0.4), "1 秒")
        self.assertEqual(run_schedule.format_remaining(-5), "0 秒")

    def test_describe(self):
        self.assertEqual(self.schedule.describe(), ("予約はありません", "予約はありません"))
        self.schedule.reserve_start(START + datetime.timedelta(minutes=90), "Python", "A連打")
        self.schedule.reserve_stop_after(20)
        start, stop = self.schedule.describe()
        self.assertEqual(start, "2026-10-11 23:30:00 に「A連打」を開始(あと 1 時間 30 分 00 秒)")
        self.assertEqual(stop, "予約した開始から 20 分後に停止")
        self.running = True
        self.schedule.reserve_stop_at(START + datetime.timedelta(seconds=30))
        self.assertEqual(self.schedule.describe()[1], "2026-10-11 22:00:30 に停止(あと 30 秒)")


if __name__ == "__main__":
    unittest.main()
