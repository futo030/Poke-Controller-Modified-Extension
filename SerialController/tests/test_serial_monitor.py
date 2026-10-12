#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/serial_monitor.py と、Sender からシリアルモニターへの受け渡しのテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import transport_scenarios  # noqa: E402
from Commands.Keys import Button, InputSource, KeyPress  # noqa: E402
from Commands.Sender import Sender  # noqa: E402
from services import serial_monitor  # noqa: E402
from services.serial_monitor import SerialMonitor, format_line  # noqa: E402

LINE = re.compile(r"^\[\d\d:\d\d:\d\d\.\d\d\d\]\[(.+?)\] (.*)$")


class SerialMonitorTest(unittest.TestCase):
    def test_line_format(self):
        stamp = time.mktime((2026, 10, 7, 12, 34, 56, 0, 0, -1)) + 0.789
        self.assertEqual(format_line(stamp, "Default", "0x0004 8"), "[12:34:56.789][Default] 0x0004 8\n")
        self.assertEqual(format_line(stamp, "NX", b"\xab\x00\x0f"), "[12:34:56.789][NX] ab 00 0f\n")
        self.assertEqual(format_line(stamp, "X", [1, 2]), "[12:34:56.789][X] [1, 2]\n")

    def test_drain_returns_the_lines_in_order_and_empties(self):
        monitor = SerialMonitor()
        monitor.add("Default", "one")
        monitor.add("DS FT (Rev3)", b"\x01\x02")
        lines = monitor.drain().splitlines()
        self.assertEqual([LINE.match(line).groups() for line in lines], [("Default", "one"), ("DS FT (Rev3)", "01 02")])
        self.assertEqual(monitor.drain(), "")

    def test_a_list_keeps_the_content_at_the_time_it_was_sent(self):
        monitor = SerialMonitor()
        values = [1, 2]
        monitor.add("X", values)
        values.append(3)
        self.assertTrue(monitor.drain().endswith("[X] [1, 2]\n"))

    def test_old_lines_are_dropped_when_nobody_reads(self):
        monitor = SerialMonitor(max_lines=3)
        for index in range(10):
            monitor.add("X", str(index))
        self.assertEqual([LINE.match(line).group(2) for line in monitor.drain().splitlines()], ["7", "8", "9"])

    def test_clear(self):
        monitor = SerialMonitor()
        monitor.add("X", "one")
        monitor.clear()
        self.assertEqual(monitor.drain(), "")

    def test_add_from_many_threads(self):
        monitor = SerialMonitor()

        def work(name):
            for index in range(200):
                monitor.add(name, str(index))

        threads = [threading.Thread(target=work, args=(f"T{n}",)) for n in range(4)]
        for thread in threads:
            thread.start()
        drained = []
        while any(thread.is_alive() for thread in threads):
            drained += monitor.drain().splitlines()
        for thread in threads:
            thread.join()
        drained += monitor.drain().splitlines()
        self.assertEqual(len(drained), 800)
        # スレッドごとの順番は保たれる
        for n in range(4):
            values = [LINE.match(line).group(2) for line in drained if f"][T{n}] " in line]
            self.assertEqual(values, [str(index) for index in range(200)])

    def test_module_does_not_import_tkinter(self):
        with io.open(serial_monitor.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("tkinter", source.replace("画面(tkinter)", ""))


class SenderTest(unittest.TestCase):
    """Show Serial にチェックを入れている間に送ったデータが、シリアルモニターに届くこと"""

    def setUp(self):
        self.original_format = KeyPress.serial_data_format_name
        self.addCleanup(lambda: setattr(KeyPress, "serial_data_format_name", self.original_format))

    def send(self, format_name: str, show: bool):
        KeyPress.serial_data_format_name = format_name
        log, stdout = [], io.StringIO()
        with contextlib.redirect_stdout(stdout):
            sender = Sender(show)
            sender.ser = transport_scenarios.FakeSerial(log)
            keys = KeyPress(sender, InputSource.COMMAND)
            keys.input([Button.A])
            keys.end()
        lines = [LINE.match(line).groups() for line in sender.monitor.drain().splitlines()]
        return log, stdout.getvalue().splitlines(), lines

    def test_monitor_collects_even_while_unchecked(self):
        # シリアルモニター(Serial タブ)には、Show Serial のチェックに関係なく、いつも渡す
        log, printed, lines = self.send("Default", False)
        self.assertTrue(log)
        sent = [entry.split(" ", 1)[1] for entry in log]
        self.assertEqual(lines, [("Default", row) for row in sent])
        # Output への表示(print)は、チェックを入れているときだけ
        self.assertEqual([line for line in printed if line in sent], [])

    def test_text_format(self):
        log, printed, lines = self.send("Default", True)
        self.assertTrue(all(entry.startswith("text ") for entry in log))
        sent = [entry.split(" ", 1)[1] for entry in log]
        self.assertEqual(lines, [("Default", row) for row in sent])
        # Output への表示は、これまでと同じ
        self.assertEqual([line for line in printed if line in sent], sent)

    def test_bytes_format(self):
        log, printed, lines = self.send("NX", True)
        self.assertTrue(any(entry.startswith("bytes ") for entry in log))
        sent = [entry.split(" ", 1)[1] for entry in log]
        self.assertEqual(lines, [("NX", row) for row in sent])


if __name__ == "__main__":
    unittest.main()
