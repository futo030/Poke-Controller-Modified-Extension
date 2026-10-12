#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/log_buffer.py(ログを、画面の Log タブに渡す受け渡し)のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import io
import logging
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import log_buffer  # noqa: E402
from services.log_buffer import LogBuffer  # noqa: E402


class LogBufferTest(unittest.TestCase):
    def setUp(self):
        self.logger = logging.Logger("test.log_buffer", logging.DEBUG)
        self.buffer = LogBuffer(max_lines=5, drain_limit=3)
        self.logger.addHandler(self.buffer)

    def test_same_text_as_the_console(self):
        # コンソールへの出力(PokeConLogger.root_logger)と同じ書式のハンドラーと比べる
        stream = io.StringIO()
        console = logging.StreamHandler(stream)
        console.setFormatter(logging.Formatter("%(asctime)s %(name)s %(funcName)s [%(levelname)s]: %(message)s"))
        self.logger.addHandler(console)
        self.logger.debug("debug %s", "引数")
        self.logger.info("情報")
        self.logger.warning("warn %d", 3)
        self.assertEqual(self.buffer.drain(), stream.getvalue())
        self.assertIn("test_same_text_as_the_console [DEBUG]: debug 引数\n", stream.getvalue())

    def test_drain_takes_everything_once(self):
        self.logger.info("a")
        self.logger.info("b")
        self.assertEqual(len(self.buffer), 2)
        self.assertEqual([line.rsplit(": ", 1)[1] for line in self.buffer.drain().splitlines()], ["a", "b"])
        self.assertEqual(self.buffer.drain(), "")

    def test_old_records_are_dropped(self):
        for i in range(8):
            self.logger.info("line %d", i)
        self.assertEqual(len(self.buffer), 5)
        text = self.buffer.drain() + self.buffer.drain()
        self.assertEqual([line.rsplit(" ", 1)[1] for line in text.splitlines()], ["3", "4", "5", "6", "7"])

    def test_drain_is_limited_per_call(self):
        for i in range(5):
            self.logger.info("line %d", i)
        self.assertEqual(len(self.buffer.drain().splitlines()), 3)
        self.assertEqual(len(self.buffer.drain().splitlines()), 2)

    def test_exception_is_kept_as_text(self):
        try:
            raise ValueError("失敗")
        except ValueError:
            self.logger.exception("error")
        # 例外つきの記録は、溜めるときに文字にする(例外が指しているものを、持ち続けない)
        self.assertIsInstance(self.buffer._entries[0], tuple)
        self.assertEqual(self.buffer._entries[0][0], logging.ERROR)
        text = self.buffer.drain()
        self.assertIn("[ERROR]: error\nTraceback", text)
        self.assertIn("ValueError: 失敗\n", text)

    def test_record_that_cannot_be_formatted_does_not_stop_the_drain(self):
        self.logger.info("bad %d", "text")
        self.logger.info("good")
        lines = self.buffer.drain().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("bad %d", lines[0])
        self.assertTrue(lines[1].endswith("good"))

    def test_level_groups(self):
        groups = [log_buffer.level_group(level) for level in (5, logging.DEBUG, logging.INFO, 25, logging.WARNING,
                                                              logging.ERROR, logging.CRITICAL)]
        self.assertEqual(groups, ["debug", "debug", "info", "info", "warning", "error", "error"])

    def test_segments_join_the_same_level_in_a_row(self):
        buffer = LogBuffer(max_lines=100, drain_limit=100)
        self.logger.addHandler(buffer)
        self.logger.debug("d1")
        self.logger.debug("d2")
        self.logger.info("i1")
        self.logger.warning("w1")
        self.logger.error("e1")
        self.logger.critical("c1")
        self.logger.debug("d3")
        segments = buffer.drain_segments()
        self.assertEqual([group for group, _ in segments], ["debug", "info", "warning", "error", "debug"])
        self.assertEqual([len(text.splitlines()) for _, text in segments], [2, 1, 1, 2, 1])
        self.assertTrue(all(text.endswith("\n") for _, text in segments))
        self.assertEqual(buffer.drain_segments(), [])

    def test_exception_lines_belong_to_the_error_segment(self):
        buffer = LogBuffer(max_lines=100, drain_limit=100)
        self.logger.addHandler(buffer)
        self.logger.info("before")
        try:
            raise ValueError("失敗")
        except ValueError:
            self.logger.exception("error")
        self.logger.info("after")
        segments = buffer.drain_segments()
        self.assertEqual([group for group, _ in segments], ["info", "error", "info"])
        self.assertIn("Traceback", segments[1][1])
        self.assertTrue(segments[1][1].endswith("ValueError: 失敗\n"))

    def test_drain_is_the_segments_joined(self):
        first, second = LogBuffer(100, 100), LogBuffer(100, 100)
        self.logger.addHandler(first)
        self.logger.addHandler(second)
        self.logger.debug("d")
        self.logger.error("e %s", "x")
        self.assertEqual(first.drain(), "".join(text for _, text in second.drain_segments()))

    def test_clear(self):
        self.logger.info("a")
        self.buffer.clear()
        self.assertEqual(self.buffer.drain(), "")

    def test_level_filter_of_the_logger_is_respected(self):
        self.logger.setLevel(logging.WARNING)
        self.logger.info("hidden")
        self.logger.warning("shown")
        self.assertEqual(len(self.buffer.drain().splitlines()), 1)

    def test_many_threads_can_log(self):
        buffer = LogBuffer(max_lines=100000, drain_limit=100000)
        self.logger.addHandler(buffer)

        def work(number):
            for i in range(500):
                self.logger.debug("%d-%d", number, i)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(buffer.drain().splitlines()), 4000)


class InstallTest(unittest.TestCase):
    def test_install_adds_the_handler_once(self):
        root = logging.getLogger()
        before = list(root.handlers)
        self.addCleanup(lambda: setattr(root, "handlers", before))
        first = log_buffer.install()
        second = log_buffer.install()
        self.assertIs(first, second)
        self.assertEqual(root.handlers.count(log_buffer.buffer), 1)


if __name__ == "__main__":
    unittest.main()
