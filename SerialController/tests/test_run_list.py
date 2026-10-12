#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/run_list.py(実行リスト: コマンドの連続実行)のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Commands.CommandBase import Command  # noqa: E402
from Commands.McuCommandBase import McuCommand  # noqa: E402
from Commands.PythonCommandBase import PythonCommand  # noqa: E402
from services import command_usage, run_list, tag_editor  # noqa: E402
from services.run_list import RunItem, RunList, RunListLoader  # noqa: E402
from services.settings_store import AppSettings  # noqa: E402


def setUpModule():
    """通知のクラスを代役にする(コマンドを作るたびに、本物の通知先へ接続を確かめに行かないようにする)"""
    for name in ("Line_Notify", "Discord_Notify"):
        patcher = mock.patch(f"Commands.PythonCommandBase.{name}")
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)

class FakeSerial:
    def __init__(self):
        self.rows = []

    def writeRow(self, row, *args, **kwargs):
        self.rows.append(row)


class FakeKeys:
    """入力を送る代わりに、呼ばれたことを記録する"""

    def __init__(self):
        self.ser = FakeSerial()
        self.calls = []

    def input(self, value):
        self.calls.append("input")

    def inputEnd(self, value):
        self.calls.append("inputEnd")

    def end(self):
        self.calls.append("end")

    def init_hat(self):
        pass


RECORD = []


class Quick(PythonCommand):
    NAME = "quick"

    def do(self):
        RECORD.append(("quick", time.perf_counter()))


class Other(PythonCommand):
    NAME = "other"

    def do(self):
        RECORD.append(("other", time.perf_counter()))


class Slow(PythonCommand):
    NAME = "slow"

    def do(self):
        RECORD.append(("slow start", time.perf_counter()))
        self.wait(30)
        RECORD.append(("slow end", time.perf_counter()))


class Broken(PythonCommand):
    NAME = "broken"

    def do(self):
        RECORD.append(("broken", time.perf_counter()))
        raise RuntimeError("boom")


class Mcu(McuCommand):
    NAME = "mcu"

    def __init__(self):
        super().__init__("MCU_SYNC")


class FakeService:
    """コマンドの名前から、クラスを返すだけの CommandService の代役"""

    classes = {"quick": Quick, "other": Other, "slow": Slow, "broken": Broken, "mcu": Mcu}

    def find_class(self, command_type, name, reload=False):
        if name == "unloadable":
            raise ImportError("cannot load")
        return self.classes.get(name)

    def create(self, command_type, command_class):
        return command_class()


def names():
    return [name for name, _ in RECORD]


class RunListCase(unittest.TestCase):
    def setUp(self):
        RECORD.clear()
        self.saved = {name: getattr(Command, name) for name in ("cur_command_name", "isPause")}
        Command.isPause = False
        Command.cur_command_name = "list (実行リスト)"
        self.addCleanup(lambda: [setattr(Command, name, value) for name, value in self.saved.items()])
        self.keys = FakeKeys()
        self.printed = io.StringIO()

    def command(self, items, **options):
        spec = RunList(name="list", items=items, **{"interval_seconds": 0, **options})
        cls = type("TestRunList", (run_list.RunListCommand,), {"RUN_LIST": spec, "SERVICE": FakeService()})
        command = cls()
        command.keys = self.keys
        command.alive = True
        command.postProcess = None
        return command

    def run_command(self, command):
        with contextlib.redirect_stdout(self.printed), contextlib.redirect_stderr(io.StringIO()):
            command.do_safe(self.keys.ser)

    def run_in_thread(self, command):
        thread = threading.Thread(target=self.run_command, args=(command,), daemon=True)
        thread.start()
        return thread


class OrderTest(RunListCase):
    def test_commands_run_in_order_with_repeats(self):
        self.run_command(self.command([RunItem("Python", "quick", repeat=2), RunItem("Python", "other")]))
        self.assertEqual(names(), ["quick", "quick", "other"])
        text = self.printed.getvalue()
        self.assertIn("[実行リスト] 1/3: quick(1/2 回目)", text)
        self.assertIn("[実行リスト] 3/3: other", text)
        self.assertIn("[実行リスト] すべて終わりました。", text)
        # 中のコマンドも、単独で実行するときと同じ、開始と終了の表示を出す
        self.assertEqual(text.count("スクリプト開始: quick"), 2)
        self.assertEqual(text.count("スクリプト開始: other"), 1)

    def test_the_whole_list_is_repeated(self):
        self.run_command(self.command([RunItem("Python", "quick"), RunItem("Python", "other")], loops=3))
        self.assertEqual(names(), ["quick", "other"] * 3)
        self.assertIn("[実行リスト] 3 周目(3 周)", self.printed.getvalue())

    def test_interval_is_waited_between_commands_but_not_after_the_last(self):
        command = self.command([RunItem("Python", "quick"), RunItem("Python", "other")], interval_seconds=0.3)
        started = time.perf_counter()
        self.run_command(command)
        elapsed = time.perf_counter() - started
        self.assertGreaterEqual(RECORD[1][1] - RECORD[0][1], 0.3)
        self.assertLess(elapsed, 0.6)

    def test_the_name_of_the_running_command_is_restored(self):
        self.run_command(self.command([RunItem("Python", "quick")]))
        self.assertEqual(Command.cur_command_name, "list (実行リスト)")
        # リストの終わりの表示は、リストの名前で出る(中のコマンドの名前のままにならない)
        self.assertTrue(self.printed.getvalue().rstrip().splitlines()[-4].endswith("スクリプト終了: list (実行リスト)"))

    def test_empty_list(self):
        self.run_command(self.command([]))
        self.assertIn("実行リストが空です。", self.printed.getvalue())


class ErrorTest(RunListCase):
    def test_error_stops_the_list_by_default(self):
        self.run_command(self.command([RunItem("Python", "broken"), RunItem("Python", "quick")]))
        self.assertEqual(names(), ["broken"])
        self.assertIn("エラーがあったので、ここで中止します。", self.printed.getvalue())

    def test_error_can_be_skipped(self):
        command = self.command([RunItem("Python", "broken"), RunItem("Python", "quick")], on_error=run_list.ON_ERROR_NEXT)
        self.run_command(command)
        self.assertEqual(names(), ["broken", "quick"])
        self.assertIn("[実行リスト] すべて終わりました。", self.printed.getvalue())

    def test_missing_and_unloadable_commands_count_as_errors(self):
        items = [RunItem("Python", "no such command"), RunItem("Python", "unloadable"), RunItem("Python", "quick")]
        self.run_command(self.command(items, on_error=run_list.ON_ERROR_NEXT))
        self.assertEqual(names(), ["quick"])
        text = self.printed.getvalue()
        self.assertIn("コマンドが見つかりません: no such command", text)
        self.assertIn("コマンドを用意できませんでした: unloadable", text)
        RECORD.clear()
        self.run_command(self.command(items))
        self.assertEqual(names(), [])

    def test_a_list_in_a_list_is_not_run(self):
        self.run_command(self.command([RunItem("Python", "inner (実行リスト)"), RunItem("Python", "quick")]))
        self.assertEqual(names(), [])
        self.assertIn("実行リストの中の実行リストは、実行しません。", self.printed.getvalue())


class LimitAndStopTest(RunListCase):
    def test_time_limit_stops_the_command_and_goes_on(self):
        command = self.command([RunItem("Python", "slow", limit_minutes=0.3 / 60), RunItem("Python", "quick")])
        started = time.perf_counter()
        self.run_command(command)
        self.assertLess(time.perf_counter() - started, 3)
        self.assertEqual(names(), ["slow start", "quick"])
        self.assertIn("制限時間", self.printed.getvalue())
        self.assertIn("になったので、止めました。", self.printed.getvalue())

    def test_limit_does_not_matter_when_the_command_ends_first(self):
        self.run_command(self.command([RunItem("Python", "quick", limit_minutes=1), RunItem("Python", "other")]))
        self.assertEqual(names(), ["quick", "other"])
        self.assertNotIn("止めました", self.printed.getvalue())

    def test_stop_ends_the_whole_list(self):
        command = self.command([RunItem("Python", "quick"), RunItem("Python", "slow"), RunItem("Python", "other")], loops=0)
        thread = self.run_in_thread(command)
        deadline = time.time() + 5
        while "slow start" not in names() and time.time() < deadline:
            time.sleep(0.01)
        with contextlib.redirect_stdout(io.StringIO()):
            command.end(self.keys.ser)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(names(), ["quick", "slow start"])
        self.assertNotIn("すべて終わりました", self.printed.getvalue())
        self.assertIn("end", self.keys.calls)

    def test_stop_during_the_interval(self):
        command = self.command([RunItem("Python", "quick"), RunItem("Python", "other")], interval_seconds=30)
        thread = self.run_in_thread(command)
        deadline = time.time() + 5
        while "quick" not in names() and time.time() < deadline:
            time.sleep(0.01)
        time.sleep(0.3)
        with contextlib.redirect_stdout(io.StringIO()):
            command.end(self.keys.ser)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(names(), ["quick"])

    def test_mcu_command_runs_for_the_time_limit(self):
        command = self.command([RunItem("Mcu", "mcu", limit_minutes=0.3 / 60), RunItem("Python", "quick")])
        started = time.perf_counter()
        self.run_command(command)
        self.assertGreaterEqual(time.perf_counter() - started, 0.3)
        self.assertEqual(self.keys.ser.rows, ["MCU_SYNC", "end"])
        self.assertEqual(names(), ["quick"])

    def test_mcu_command_is_stopped_with_the_list(self):
        command = self.command([RunItem("Mcu", "mcu", limit_minutes=10), RunItem("Python", "quick")])
        thread = self.run_in_thread(command)
        deadline = time.time() + 5
        while not self.keys.ser.rows and time.time() < deadline:
            time.sleep(0.01)
        with contextlib.redirect_stdout(io.StringIO()):
            command.end(self.keys.ser)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.keys.ser.rows, ["MCU_SYNC", "end"])
        self.assertEqual(names(), [])

    def test_mcu_command_without_a_limit_is_an_error(self):
        self.run_command(self.command([RunItem("Mcu", "mcu")]))
        self.assertEqual(self.keys.ser.rows, [])
        self.assertIn("Mcu コマンドには、制限時間が要ります。", self.printed.getvalue())


class CheckTest(unittest.TestCase):
    def test_valid_list(self):
        items = [RunItem("Python", "a"), RunItem("Mcu", "m", repeat=3, limit_minutes=1.5)]
        self.assertEqual(run_list.check_list(RunList("毎日の作業", items, interval_seconds=0, loops=0)), "")

    def test_invalid_lists_tell_the_reason(self):
        good = [RunItem("Python", "a")]
        cases = [
            (RunList("", good), "名前"),
            (RunList("x" * 51, good), "50"),
            (RunList("a\nb", good), "改行"),
            (RunList("taken", good), "すでに"),
            (RunList("n", []), "1 つ以上"),
            (RunList("n", [RunItem("Other", "a")]), "種類"),
            (RunList("n", [RunItem("Python", "")]), "選んで"),
            (RunList("n", [RunItem("Python", "x (実行リスト)")]), "入れられません"),
            (RunList("n", [RunItem("Python", "a", repeat=0)]), "回数"),
            (RunList("n", [RunItem("Python", "a", repeat=1.5)]), "回数"),
            (RunList("n", [RunItem("Python", "a", limit_minutes=0)]), "制限時間"),
            (RunList("n", [RunItem("Mcu", "m")]), "Mcu"),
            (RunList("n", good, interval_seconds=-1), "待ち時間"),
            (RunList("n", good, on_error="x"), "エラー"),
            (RunList("n", good, loops=-1), "繰り返し"),
        ]
        for spec, word in cases:
            with self.subTest(word=word):
                self.assertIn(word, run_list.check_list(spec, ["taken"]))
        self.assertTrue(run_list.check_list(RunList("n", [RunItem("Python", "a"), RunItem("Mcu", "m")])).startswith("2 行目"))

    def test_parse_number(self):
        self.assertEqual(run_list.parse_number(" 1.5 "), 1.5)
        self.assertIsNone(run_list.parse_number("  ", allow_empty=True))
        for text in ("", "abc", "nan", "inf"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                run_list.parse_number(text)

    def test_list_names_in_the_command_list(self):
        self.assertTrue(run_list.is_list_name("Python", "x (実行リスト)"))
        self.assertFalse(run_list.is_list_name("Mcu", "x (実行リスト)"))
        self.assertFalse(run_list.is_list_name("Python", "x (Samples/x)"))
        self.assertEqual(RunList("x").display_name, "x (実行リスト)")


class FileTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))
        patcher = mock.patch.object(AppSettings, "SETTING_PATH", os.path.join(self.directory, "profile", "settings.ini"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = os.path.join(self.directory, "profile", "run_lists.json")

    def test_the_file_is_next_to_the_settings_of_the_profile(self):
        self.assertEqual(run_list.lists_path(), self.path)

    def test_missing_file_means_no_lists(self):
        self.assertEqual(run_list.load_lists(), [])

    def test_save_and_load(self):
        lists = [
            RunList("朝", [RunItem("Python", "A連打 (Samples/mash)", 2, 1.5), RunItem("Mcu", "m", 1, 10)], 2.5, "next", 0),
            RunList("夜", [RunItem("Python", "b")]),
        ]
        run_list.save_lists(lists)
        self.assertEqual(run_list.load_lists(), lists)
        self.assertEqual([name for name in os.listdir(os.path.dirname(self.path)) if name.endswith(".tmp")], [])

    def test_broken_file_and_bad_lists_are_skipped(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as file:
            file.write("{ broken")
        with self.assertLogs(run_list._logger, "WARNING"):
            self.assertEqual(run_list.load_lists(), [])
        rows = [
            {"name": "ok", "items": [{"type": "Python", "name": "a"}]},
            {"name": "ok", "items": [{"type": "Python", "name": "a"}]},
            {"name": "no items", "items": []},
            {"items": [{"type": "Python", "name": "a"}]},
            "text",
            {"name": "mcu without limit", "items": [{"type": "Mcu", "name": "m"}]},
        ]
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({"version": 1, "lists": rows}, file)
        with self.assertLogs(run_list._logger, "WARNING"):
            loaded = run_list.load_lists()
        self.assertEqual([item.name for item in loaded], ["ok"])
        self.assertEqual(loaded[0].items, [RunItem("Python", "a")])

    def test_loader_adds_the_lists_to_the_command_list(self):
        run_list.save_lists([RunList("朝", [RunItem("Python", "quick")]), RunList("夜", [RunItem("Python", "other")])])
        loader = RunListLoader(FakeService())
        entries = loader.load()
        self.assertEqual([entry.name for entry in entries], ["朝 (実行リスト)", "夜 (実行リスト)"])
        self.assertEqual(entries[0].tags, ["@実行リスト"])
        self.assertEqual(entries[0].file_path, self.path)
        self.assertIs(loader.findEntry("夜 (実行リスト)"), entries[1])
        self.assertIsNone(loader.findEntry("quick"))
        command_class = loader.getCommandClass(entries[0])
        self.assertTrue(issubclass(command_class, run_list.RunListCommand))
        self.assertEqual((command_class.NAME, command_class.RUN_LIST.items), ("朝 (実行リスト)", [RunItem("Python", "quick")]))
        # 読み直すと、消したリストはなくなる
        run_list.save_lists([RunList("夜", [RunItem("Python", "other")])])
        self.assertEqual([entry.name for entry in loader.reload()], ["夜 (実行リスト)"])
        with self.assertRaises(ImportError):
            loader.getCommandClass(entries[0])

    def test_lists_work_with_the_usage_count_and_the_tag_editor(self):
        run_list.save_lists([RunList("朝", [RunItem("Python", "quick")])])
        entry = RunListLoader(FakeService()).load()[0]
        key = command_usage.usage_key("Python", entry)
        self.assertEqual((key[0], key[1]), ("Python", "朝"))
        self.assertTrue(key[2].endswith("run_lists.json"))
        # タグの編集画面では、編集できないコマンドとして扱う(例外にならない)
        source = tag_editor.read_source(entry.file_path, entry.class_name)
        self.assertFalse(source.editable)


if __name__ == "__main__":
    unittest.main()
