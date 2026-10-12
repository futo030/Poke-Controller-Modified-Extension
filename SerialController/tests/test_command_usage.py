#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/command_usage.py(コマンドを実行した回数の記録)と、使用頻度での並び替えのテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from CommandLoader import CommandEntry  # noqa: E402
from services import command_catalog, command_usage  # noqa: E402
from services.command_service import CommandService  # noqa: E402
from services.tools_service import ToolsService  # noqa: E402


def entry(name, file_path):
    return CommandEntry(name=name, file_path=file_path)


MASH = entry("A連打 (Samples/mash)", os.path.join("Commands", "PythonCommands", "Samples", "mash.py"))
MASH_FILE = "Commands/PythonCommands/Samples/mash.py"


class UsageKeyTest(unittest.TestCase):
    def test_key_is_type_name_and_file_location(self):
        self.assertEqual(command_usage.usage_key("Python", MASH), ("Python", "A連打", MASH_FILE))

    def test_folders_are_told_apart(self):
        moved = entry("A連打 (Mine/Sub/mash)", os.path.join("Commands", "PythonCommands", "Mine", "Sub", "mash.py"))
        top = entry("A連打 (mash)", os.path.join("Commands", "PythonCommands", "mash.py"))
        self.assertEqual(command_usage.usage_key("Python", moved), ("Python", "A連打", "Commands/PythonCommands/Mine/Sub/mash.py"))
        self.assertEqual(command_usage.usage_key("Python", top), ("Python", "A連打", "Commands/PythonCommands/mash.py"))

    def test_same_file_written_in_another_way_is_the_same_key(self):
        absolute = entry(MASH.name, os.path.join(BASE_DIR, MASH.file_path))
        slashes = entry(MASH.name, MASH.file_path.replace(os.sep, "/"))
        self.assertEqual(command_usage.usage_key("Python", absolute), command_usage.usage_key("Python", MASH))
        self.assertEqual(command_usage.usage_key("Python", slashes), command_usage.usage_key("Python", MASH))

    def test_name_or_file_name_change_makes_another_key(self):
        renamed = entry("B連打 (Samples/mash)", MASH.file_path)
        other_file = entry("A連打 (Samples/mash2)", os.path.join("Commands", "PythonCommands", "Samples", "mash2.py"))
        keys = {command_usage.usage_key("Python", e) for e in (MASH, renamed, other_file)}
        self.assertEqual(len(keys), 3)
        self.assertNotEqual(command_usage.usage_key("Mcu", MASH), command_usage.usage_key("Python", MASH))

    def test_parentheses_in_the_name_and_the_folder(self):
        named = entry("孵化 (v2) (Samples/egg)", os.path.join("Commands", "PythonCommands", "Samples", "egg.py"))
        folder = entry("孵化 (My (old)/egg)", os.path.join("Commands", "PythonCommands", "My (old)", "egg.py"))
        self.assertEqual(command_usage.usage_key("Python", named), ("Python", "孵化 (v2)", "Commands/PythonCommands/Samples/egg.py"))
        self.assertEqual(command_usage.usage_key("Python", folder), ("Python", "孵化", "Commands/PythonCommands/My (old)/egg.py"))

    def test_name_not_made_from_the_file_path(self):
        self.assertEqual(
            command_usage.usage_key("Python", entry("マクロ (ext)", os.path.join("somewhere", "マクロ.bin"))),
            ("Python", "マクロ", "somewhere/マクロ.bin"),
        )
        self.assertEqual(command_usage.usage_key("Python", SimpleNamespace(name="NoFile")), ("Python", "NoFile", ""))


class UsageFileTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))
        self.path = os.path.join(self.directory, "profiles", "command_usage.json")

    def test_missing_file_means_zero(self):
        self.assertEqual(command_usage.load(self.path), {})
        self.assertEqual(command_usage.counts_of("Python", [MASH], self.path), {MASH.name: 0})

    def test_record_adds_one_and_is_kept_in_the_file(self):
        other = entry("B (b)", os.path.join("Commands", "PythonCommands", "b.py"))
        for e in (MASH, MASH, other, MASH):
            self.assertTrue(command_usage.record("Python", e, self.path))
        self.assertEqual(command_usage.counts_of("Python", [MASH, other], self.path), {MASH.name: 3, other.name: 1})
        # 種別が違えば、別に数える
        self.assertEqual(command_usage.counts_of("Mcu", [MASH], self.path), {MASH.name: 0})
        with open(self.path, encoding="utf-8") as file:
            data = json.load(file)
        self.assertIn({"type": "Python", "name": "A連打", "file": MASH_FILE, "count": 3}, data["commands"])
        self.assertFalse(os.path.exists(self.path + ".lock"))
        self.assertEqual([n for n in os.listdir(os.path.dirname(self.path)) if n.endswith(".tmp")], [])

    def test_load_sees_what_another_writer_wrote(self):
        command_usage.record("Python", MASH, self.path)
        self.assertEqual(command_usage.load(self.path)[("Python", "A連打", MASH_FILE)], 1)
        time.sleep(0.01)
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({"version": 1, "commands": [{"type": "Python", "name": "A連打", "file": MASH_FILE, "count": 40}]}, file)
        self.assertEqual(command_usage.load(self.path)[("Python", "A連打", MASH_FILE)], 40)

    def test_broken_file_is_set_aside(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as file:
            file.write("{ broken")
        with self.assertLogs(command_usage._logger, "WARNING"):
            self.assertEqual(command_usage.load(self.path), {})
        self.assertTrue(command_usage.record("Python", MASH, self.path))
        self.assertTrue(os.path.exists(self.path + ".broken"))
        self.assertEqual(command_usage.counts_of("Python", [MASH], self.path), {MASH.name: 1})

    def test_rows_of_unexpected_shape_are_skipped(self):
        os.makedirs(os.path.dirname(self.path))
        rows = [{"type": "Python", "name": "A連打", "file": "mash.py", "count": 2}, {"name": "x"}, "text", {"type": "Python", "name": "y", "file": "y.py", "count": "many"}]
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({"version": 1, "commands": rows}, file)
        self.assertEqual(command_usage.load(self.path), {("Python", "A連打", "mash.py"): 2})

    def test_held_lock_does_not_stop_the_caller(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path + ".lock", "w"):
            pass
        with mock.patch.object(command_usage, "LOCK_WAIT", 0.05), self.assertLogs(command_usage._logger, "WARNING"):
            self.assertFalse(command_usage.record("Python", MASH, self.path))
        self.assertTrue(os.path.exists(self.path + ".lock"))

    def test_stale_lock_is_removed(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path + ".lock", "w"):
            pass
        old = time.time() - command_usage.LOCK_STALE - 10
        os.utime(self.path + ".lock", (old, old))
        self.assertTrue(command_usage.record("Python", MASH, self.path))
        self.assertFalse(os.path.exists(self.path + ".lock"))

    def test_several_processes_do_not_lose_counts(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1])\n"
            "from types import SimpleNamespace\n"
            "from services import command_usage\n"
            "command_usage.LOCK_WAIT = 30\n"
            "e = SimpleNamespace(name='A (a)', file_path='a.py')\n"
            "sys.exit(0 if all(command_usage.record('Python', e, sys.argv[2]) for _ in range(25)) else 1)\n"
        )
        processes = [subprocess.Popen([sys.executable, "-c", code, BASE_DIR, self.path]) for _ in range(4)]
        self.assertEqual([p.wait(timeout=120) for p in processes], [0, 0, 0, 0])
        self.assertEqual(command_usage.load(self.path), {("Python", "A", "a.py"): 100})


class UsageSortTest(unittest.TestCase):
    def setUp(self):
        self.commands = [entry(name, f"{name}.py") for name in ("a", "b", "c", "d")]
        self.counts = {"a": 0, "b": 5, "c": 0, "d": 2}

    def names(self, sort, usage_of="default"):
        if usage_of == "default":
            def usage_of(c):
                return self.counts[c.name]
        return [c.name for _, c in command_catalog.filter_commands(self.commands, sort=sort, usage_of=usage_of)]

    def test_most_used_first(self):
        self.assertEqual(self.names("usage_desc"), ["b", "d", "a", "c"])

    def test_least_used_first(self):
        self.assertEqual(self.names("usage_asc"), ["a", "c", "d", "b"])

    def test_without_counts_the_order_is_kept(self):
        self.assertEqual(self.names("usage_desc", usage_of=None), ["a", "b", "c", "d"])

    def test_original_numbers_are_kept(self):
        rows = command_catalog.filter_commands(self.commands, sort="usage_desc", usage_of=lambda c: self.counts[c.name])
        self.assertEqual([i for i, _ in rows], [1, 3, 0, 2])


class FakeLoader:
    def __init__(self, entries):
        self.entries = {e.name: e for e in entries}

    def findEntry(self, name):
        return self.entries.get(name)


class ServiceUsageTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))
        patcher = mock.patch.object(command_usage, "USAGE_PATH", os.path.join(self.directory, "command_usage.json"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = CommandService(lambda: None, lambda: None)
        self.other = entry("B (b)", "b.py")
        self.service.loaders = {"Python": FakeLoader([MASH, self.other]), "Mcu": FakeLoader([])}
        self.service.commands = {"Python": [MASH, self.other], "Mcu": []}

    def test_record_and_counts(self):
        self.service.record_usage("py", MASH.name)
        self.service.record_usage("Python", MASH.name)
        self.service.record_usage("Python", "no such command")
        self.service.record_usage("Other", MASH.name)
        self.assertEqual(self.service.usage_counts("Python"), {MASH.name: 2, self.other.name: 0})
        self.assertEqual(self.service.usage_counts("Mcu"), {})

    def test_two_services_share_the_counts(self):
        second = CommandService(lambda: None, lambda: None)
        second.loaders, second.commands = self.service.loaders, self.service.commands
        self.service.record_usage("Python", MASH.name)
        second.record_usage("Python", MASH.name)
        self.assertEqual(self.service.usage_counts("Python")[MASH.name], 2)

    def test_tools_state_has_the_counts(self):
        self.service.record_usage("Python", self.other.name)
        tools = ToolsService(SimpleNamespace(commands=self.service))
        self.assertEqual(tools.command_usage(), {"Python": {MASH.name: 0, self.other.name: 1}, "Mcu": {}})


if __name__ == "__main__":
    unittest.main()
