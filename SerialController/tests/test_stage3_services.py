#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/command_catalog.py・geometry.py・record_service.py のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import command_catalog, geometry, record_service  # noqa: E402
from services.record_service import RecordError, RecordService  # noqa: E402


def entry(name, *tags):
    return SimpleNamespace(name=name, tags=list(tags))


class CommandCatalogTest(unittest.TestCase):
    def setUp(self):
        self.commands = [entry("Beta", "raid", "@Samples"), entry("alpha", "egg"), entry("Gamma", "raid", "@Mine")]

    def names(self, **options):
        return [(i, c.name) for i, c in command_catalog.filter_commands(self.commands, **options)]

    def test_directory_tags_come_last(self):
        self.assertEqual(command_catalog.sort_tags(self.commands), ["egg", "raid", "@Mine", "@Samples"])

    def test_default_order_keeps_the_original_numbers(self):
        self.assertEqual(self.names(), [(0, "Beta"), (1, "alpha"), (2, "Gamma")])

    def test_sort_by_name_ignores_case(self):
        self.assertEqual(self.names(sort="name_asc"), [(1, "alpha"), (0, "Beta"), (2, "Gamma")])
        self.assertEqual(self.names(sort="name_desc"), [(2, "Gamma"), (0, "Beta"), (1, "alpha")])

    def test_sort_by_modified_time(self):
        mtimes = {"Beta": 3.0, "alpha": 1.0, "Gamma": 2.0}
        self.assertEqual(
            self.names(sort="mtime_desc", mtime_of=lambda c: mtimes[c.name]), [(0, "Beta"), (2, "Gamma"), (1, "alpha")]
        )

    def test_filters(self):
        self.assertEqual(self.names(tags={"egg", "@Mine"}), [(1, "alpha"), (2, "Gamma")])
        self.assertEqual(self.names(name_filter=" AM "), [(2, "Gamma")])
        self.assertEqual(self.names(tags={"raid"}, name_filter="be"), [(0, "Beta")])
        self.assertEqual(self.names(tags={"none"}), [])

    def test_normalize_command_type(self):
        for text in ("Python", "PYTHON", "python", "Py", "PY", "py"):
            self.assertEqual(command_catalog.normalize_command_type(text), "Python")
        for text in ("Mcu", "MCU", "mcu"):
            self.assertEqual(command_catalog.normalize_command_type(text), "Mcu")
        self.assertEqual(command_catalog.normalize_command_type("None"), "None")

    def test_find_named_command(self):
        find = command_catalog.find_named_command
        self.assertEqual(find("py", "A", ["A"], ["M"]), ("Python", ""))
        self.assertEqual(find("MCU", "M", ["A"], ["M"]), ("Mcu", ""))
        self.assertEqual(find("Python", "X", ["A"], ["M"]), (None, "Python command name error."))
        self.assertEqual(find("Mcu", "A", ["A"], ["M"]), (None, "Mcu command name error."))
        self.assertEqual(find("Other", "A", ["A"], ["M"]), (None, "command type error."))

    def test_history_moves_the_same_command_to_the_top_and_drops_old_ones(self):
        history = []
        for minute, name in enumerate(["A", "B", "C", "A"]):
            command_catalog.add_history(history, "py", name, 3, now=datetime(2026, 10, 5, 12, minute, 0))
        self.assertEqual([h["name"] for h in history], ["A", "C", "B"])
        self.assertEqual(history[0], {"class": "Python", "name": "A", "last_run": "2026-10-05 12:03:00"})
        command_catalog.add_history(history, "Mcu", "A", 3, now=datetime(2026, 10, 5, 12, 4, 0))
        self.assertEqual([(h["class"], h["name"]) for h in history], [("Mcu", "A"), ("Python", "A"), ("Python", "C")])

    def test_sorted_history(self):
        history = [{"name": "old", "last_run": "2026-10-01 00:00:00"}, {"name": "new", "last_run": "2026-10-05 00:00:00"}]
        self.assertEqual([i for i, _ in command_catalog.sorted_history(history, True)], [1, 0])
        self.assertEqual([i for i, _ in command_catalog.sorted_history(history, False)], [0, 1])


class GeometryTest(unittest.TestCase):
    def test_clamp_area(self):
        self.assertEqual(geometry.clamp_area(-5, 10, 2000, 700, 1280, 720), (0, 10, 1280, 700))
        self.assertEqual(geometry.clamp_area(10, 20, 30, 40, 1280, 720), (10, 20, 30, 40))
        self.assertIsNone(geometry.clamp_area(30, 20, 30, 40, 1280, 720))
        self.assertIsNone(geometry.clamp_area(1300, 20, 1400, 40, 1280, 720))
        self.assertIsNone(geometry.clamp_area(10, 50, 30, 40, 1280, 720))

    def test_ratio_round_trip(self):
        ratio = geometry.area_to_ratio((64, 36, 320, 180), 640, 360)
        self.assertEqual(ratio, (0.1, 0.1, 0.5, 0.5))
        self.assertEqual(geometry.ratio_to_area(ratio, 1280, 720), (128, 72, 640, 360))
        self.assertEqual(geometry.ratio_to_area(ratio, 640, 360), (64, 36, 320, 180))

    def test_ratio_text(self):
        self.assertEqual(geometry.ratio_to_text(None), "")
        text = geometry.ratio_to_text((0.1, 0.25, 1 / 3, 1))
        self.assertEqual(geometry.parse_ratio(text), (0.1, 0.25, 1 / 3, 1.0))
        for bad in ("", "a,b,c,d", "0.1,0.2,0.3", "0.1,0.2,0.3,1.5", "-0.1,0.2,0.3,0.4"):
            self.assertIsNone(geometry.parse_ratio(bad), bad)

    def test_ratio_matches_area(self):
        ratio = (0.1, 0.1, 0.5, 0.5)
        self.assertTrue(geometry.ratio_matches_area(ratio, (64, 36, 320, 180), 640, 360))
        self.assertTrue(geometry.ratio_matches_area(ratio, (65, 36, 319, 180), 640, 360))
        self.assertFalse(geometry.ratio_matches_area(ratio, (70, 36, 320, 180), 640, 360))

    def test_size_for_height(self):
        self.assertEqual(geometry.size_for_height(360, 16 / 9, 100), (640, 360))
        self.assertEqual(geometry.size_for_height(50.4, 16 / 9, 100), (178, 100))
        self.assertEqual(geometry.size_for_height(384, 256 / 384, 100), (256, 384))

    def test_is_valid_size_text(self):
        self.assertTrue(geometry.is_valid_size_text("640x360", 16 / 9, 100))
        self.assertTrue(geometry.is_valid_size_text("604X340", 16 / 9, 100))
        self.assertFalse(geometry.is_valid_size_text("640x480", 16 / 9, 100))
        self.assertFalse(geometry.is_valid_size_text("160x90", 16 / 9, 100))
        self.assertFalse(geometry.is_valid_size_text("wide", 16 / 9, 100))


class FakeRecorder:
    instances = []
    start_error = None
    stop_result = "script.py"

    def __init__(self, source_name, raw_log_dir):
        self.source_name = source_name
        self.raw_log_dir = raw_log_dir
        self.raw_log_path = None
        FakeRecorder.instances.append(self)

    def start(self):
        if FakeRecorder.start_error is not None:
            raise FakeRecorder.start_error
        self.raw_log_path = os.path.join(self.raw_log_dir, "record.csv")

    def stop(self):
        if isinstance(FakeRecorder.stop_result, Exception):
            raise FakeRecorder.stop_result
        return FakeRecorder.stop_result


class FakeSender:
    def __init__(self, opened=True):
        self.opened = opened
        self.recorder = None

    def isOpened(self):
        return self.opened

    @property
    def recording(self):
        return self.recorder is not None

    def start_recording(self, recorder):
        self.recorder = recorder

    def stop_recording(self):
        recorder, self.recorder = self.recorder, None
        return recorder


class RecordServiceTest(unittest.TestCase):
    def setUp(self):
        FakeRecorder.instances = []
        FakeRecorder.start_error = None
        FakeRecorder.stop_result = "script.py"
        patcher = mock.patch.object(record_service, "InputRecorder", FakeRecorder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.running = False
        self.sender = FakeSender()
        self.service = RecordService(self.sender, lambda: self.running, "logs")

    def test_start_and_stop(self):
        recorder = self.service.start()
        self.assertEqual((recorder.source_name, recorder.raw_log_dir), ("手動操作", "logs"))
        self.assertTrue(self.service.is_recording())
        result = self.service.stop()
        self.assertEqual((result.recorded, result.path, result.error), (True, "script.py", None))
        self.assertEqual(result.raw_log_path, os.path.join("logs", "record.csv"))
        self.assertFalse(self.service.is_recording())

    def test_cannot_start_while_a_command_is_running(self):
        self.running = True
        with self.assertRaises(RecordError) as raised:
            self.service.start()
        self.assertEqual(str(raised.exception), "コマンド実行中は操作記録を開始できません。")
        self.assertEqual(FakeRecorder.instances, [])

    def test_cannot_start_without_a_connection(self):
        self.sender.opened = False
        with self.assertRaises(RecordError) as raised:
            self.service.start()
        self.assertEqual(str(raised.exception), "シリアルが接続されていないため、操作記録を開始できません。")

    def test_log_file_error(self):
        FakeRecorder.start_error = OSError("disk full")
        with self.assertRaises(RecordError) as raised:
            self.service.start()
        self.assertEqual(str(raised.exception), "操作記録を開始できませんでした: disk full")
        self.assertFalse(self.service.is_recording())

    def test_stop_without_recording(self):
        self.assertEqual(self.service.stop().recorded, False)

    def test_nothing_recorded(self):
        FakeRecorder.stop_result = None
        self.service.start()
        result = self.service.stop()
        self.assertEqual((result.recorded, result.path, result.error), (True, None, None))

    def test_conversion_error_keeps_the_raw_log(self):
        FakeRecorder.stop_result = ValueError("broken")
        self.service.start()
        result = self.service.stop()
        self.assertTrue(result.recorded)
        self.assertIsNone(result.path)
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(result.raw_log_path, os.path.join("logs", "record.csv"))


if __name__ == "__main__":
    unittest.main()
