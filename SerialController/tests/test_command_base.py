#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commands/CommandBase.py と services/dialogue_store.py のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERIAL_CONTROLLER_DIR)

from Commands.CommandBase import Command  # noqa: E402
from services import dialogue_store  # noqa: E402


class FakeCommand(Command):
    """終了したかを記録するだけのコマンド"""

    def __init__(self):
        super().__init__()
        self.finished = False

    def finish(self):
        self.finished = True


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class DialogueTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.answer = ["value"]
        self.original_handler = Command.dialogue_handler
        self.original_pos = Command.pos_dialogue_buttons
        Command.dialogue_handler = self.handler
        self.directory = tempfile.mkdtemp()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        Command.dialogue_handler = self.original_handler
        Command.pos_dialogue_buttons = self.original_pos
        shutil.rmtree(self.directory, ignore_errors=True)

    def handler(self, command, title, message, desc=None, need=list, mode=0, pos=2):
        self.calls.append({"title": title, "message": message, "desc": desc, "need": need, "mode": mode, "pos": pos})
        return self.answer(self.calls[-1]) if callable(self.answer) else self.answer

    def test_dialogue_returns_the_input(self):
        command = FakeCommand()
        Command.pos_dialogue_buttons = "1"
        self.assertEqual(command.dialogue("Title", ["a"], desc="note"), ["value"])
        self.assertEqual(
            self.calls, [{"title": "Title", "message": ["a"], "desc": "note", "need": list, "mode": 0, "pos": 1}]
        )
        self.assertFalse(command.finished)

    def test_cancel_finishes_the_command(self):
        command = FakeCommand()
        self.answer = False
        self.assertIsNone(command.dialogue("Title", "a"))
        self.assertTrue(command.finished)

    def test_dialogue6widget_uses_widget_mode(self):
        command = FakeCommand()
        widgets = [["Entry", "name", "x"], ["Check", "flag", True]]
        self.assertEqual(command.dialogue6widget("Title", widgets, need=dict), ["value"])
        self.assertEqual(self.calls[0]["mode"], 1)
        self.assertIs(self.calls[0]["need"], dict)

    def test_duplicate_widget_names_finish_the_command(self):
        command = FakeCommand()
        with quiet():
            command.dialogue6widget("Title", [["Entry", "name", "x"], ["Entry", "name", "y"]])
        self.assertTrue(command.finished)

    def test_save_settings_restores_the_previous_input(self):
        filename = os.path.join(self.directory, "saved", "settings.json")
        widgets = [["Entry", "name", "default"], ["Check", "flag", False]]
        self.answer = ["typed", True]
        with quiet():
            self.assertEqual(FakeCommand().dialogue6widget_save_settings("Title", widgets, filename), ["typed", True])
        with open(filename, encoding="utf-8") as file:
            self.assertEqual(json.load(file), {"name": "typed", "flag": True})

        # 次に開くときは、保存した値が初期値になる
        widgets = [["Entry", "name", "default"], ["Check", "flag", False]]
        FakeCommand().dialogue6widget_save_settings("Title", widgets, filename)
        self.assertEqual(self.calls[-1]["message"], [["Entry", "name", "typed"], ["Check", "flag", True]])

    def test_select_settings_saves_a_preset(self):
        widgets = [["Entry", "name", "default"]]

        def answer(call):
            if call["title"] == "Select Preset":
                return ["(選択して下さい)"]
            return ["typed", "my preset", True]

        self.answer = answer
        with quiet():
            ret = FakeCommand().dialogue6widget_select_settings("Title", widgets, self.directory)
        self.assertEqual(ret, ["typed"])
        self.assertEqual([call["title"] for call in self.calls], ["Select Preset", "Title"])
        # 設定の保存用のウィジェットが足されている
        self.assertEqual([w[1] for w in self.calls[1]["message"]], ["name", "[PokeCon]設定ファイル名", "[PokeCon]設定を保存"])
        for name in ("my preset.json", "前回の設定.json"):
            with open(os.path.join(self.directory, name), encoding="utf-8") as file:
                self.assertEqual(json.load(file), {"name": "typed"})
        self.assertEqual(sorted(dialogue_store.get_settings_list(self.directory)), ["my preset", "前回の設定"])


class DialogueStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))

    def test_check_widget_name(self):
        self.assertTrue(dialogue_store.check_widget_name([["Entry", "a", ""], ["Entry", "b", ""], ["Next"]]))
        self.assertFalse(dialogue_store.check_widget_name([["Entry", "a", ""], ["Entry", "a", ""]]))
        self.assertFalse(dialogue_store.check_widget_name([["Entry", "a", ""]], except_name=["a"]))

    def test_missing_file_keeps_the_defaults(self):
        widgets = [["Entry", "a", "default"]]
        self.assertIsNone(dialogue_store.get_setting(os.path.join(self.directory, "none.json")))
        self.assertEqual(dialogue_store.generate_new_dialogue_list(widgets, None), [["Entry", "a", "default"]])

    def test_dict_result_is_saved_as_is(self):
        filename = os.path.join(self.directory, "a.json")
        dialogue_store.save_dialogue_settings([["Entry", "a", ""]], {"a": "あ"}, filename)
        self.assertEqual(dialogue_store.get_setting(filename), {"a": "あ"})

    def test_settings_list_skips_hidden_files_and_creates_the_folder(self):
        folder = os.path.join(self.directory, "presets")
        self.assertEqual(dialogue_store.get_settings_list(folder), [])
        self.assertTrue(os.path.isdir(folder))
        for name in ("one.json", "_hidden.json", "note.txt"):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as file:
                file.write("{}")
        self.assertEqual(dialogue_store.get_settings_list(folder), ["one"])

    def test_old_import_path_still_works(self):
        # これまでの import (PokeConDialogue から) は、画面のある環境で使える
        with io.open(os.path.join(SERIAL_CONTROLLER_DIR, "PokeConDialogue.py"), encoding="utf-8") as file:
            source = file.read()
        for name in ("check_widget_name", "generate_new_dialogue_list", "save_dialogue_settings", "get_settings_list"):
            self.assertIn(name, source)


class OutputPageTest(unittest.TestCase):
    def test_main_thread_has_no_page(self):
        self.assertIsNone(Command.get_output_page_for_current_thread())

    def test_page_can_be_set_temporarily(self):
        with Command.output_to_page(2):
            self.assertEqual(Command.get_output_page_for_current_thread(), 2)
            with Command.output_to_page(1):
                self.assertEqual(Command.get_output_page_for_current_thread(), 1)
            self.assertEqual(Command.get_output_page_for_current_thread(), 2)
        self.assertIsNone(Command.get_output_page_for_current_thread())

    def test_command_thread_and_its_sub_thread_use_the_registered_page(self):
        pages = {}

        def sub():
            pages["sub"] = Command.get_output_page_for_current_thread()

        def work():
            Command.register_output_thread(2)
            try:
                pages["command"] = Command.get_output_page_for_current_thread()
                thread = threading.Thread(target=sub)
                thread.start()
                thread.join()
            finally:
                Command.unregister_output_thread()
            pages["after"] = Command.get_output_page_for_current_thread()

        thread = threading.Thread(target=work)
        thread.start()
        thread.join()
        self.assertEqual(pages, {"command": 2, "sub": 2, "after": None})


class ImportTest(unittest.TestCase):
    def test_command_modules_do_not_load_tkinter(self):
        code = (
            "import sys\n"
            "import Commands.CommandBase, Commands.PythonCommandBase, Commands.McuCommandBase, Commands.UnitCommand\n"
            "import services.command_service, services.dialogue_store\n"
            "sys.stderr.write('TKINTER=' + str('tkinter' in sys.modules))\n"
        )
        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", code], cwd=SERIAL_CONTROLLER_DIR, capture_output=True, timeout=120
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace")[-500:])
        self.assertIn(b"TKINTER=False", result.stderr)


if __name__ == "__main__":
    unittest.main()
