#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/command_service.py のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Commands import McuCommandBase, PythonCommandBase  # noqa: E402
from Commands.CommandBase import Command  # noqa: E402
from services import command_service  # noqa: E402
from services.command_service import IDLE, RUNNING, STOPPING, CommandLoadError, CommandService  # noqa: E402


def setUpModule():
    """通知のクラスを代役にする(コマンドを作るたびに、本物の通知先へ接続を確かめに行かないようにする)"""
    for name in ("Line_Notify", "Discord_Notify"):
        patcher = mock.patch(f"Commands.PythonCommandBase.{name}")
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)

class FakeEntry:
    def __init__(self, name, command_class=None, error=None):
        self.name = name
        self.module_name = f"module_of_{name}"
        self.file_path = f"{name}.py"
        self.command_class = command_class
        self.error = error


class FakeLoader:
    def __init__(self, entries):
        self.entries = entries
        self.reload_count = 0
        self.loaded = []

    def load(self):
        return self.entries

    def reload(self):
        self.reload_count += 1
        return self.entries

    def findEntry(self, name):
        return next((entry for entry in self.entries if entry.name == name), None)

    def getCommandClass(self, entry, reload=False):
        self.loaded.append((entry.name, reload))
        if entry.error is not None:
            raise entry.error
        return entry.command_class


class RecordingCommand:
    """start / end の呼び出しを記録するコマンドの代役"""

    NAME = "recording"

    def __init__(self):
        self.calls = []
        self.post_process = None

    def start(self, ser, postProcess=None):
        self.calls.append(("start", ser))
        self.post_process = postProcess

    def end(self, ser):
        self.calls.append(("end", ser))


class SynchronousCommand(RecordingCommand):
    """Mcuコマンドのように、end の中で終了を知らせるコマンドの代役"""

    def end(self, ser):
        super().end(ser)
        self.post_process()


class PlainPython(PythonCommandBase.PythonCommand):
    NAME = "plain"

    def do(self):
        pass


class ImageNew(PythonCommandBase.ImageProcPythonCommand):
    NAME = "image_new"

    def __init__(self, cam, gui=None):
        super().__init__(cam, gui)
        self.received = (cam, gui)

    def do(self):
        pass


class ImageOld(PythonCommandBase.ImageProcPythonCommand):
    """プレビューを受け取らない、以前の書き方のコマンド"""

    NAME = "image_old"

    def __init__(self, cam):
        super().__init__(cam)
        self.received = (cam,)

    def do(self):
        pass


class Mcu(McuCommandBase.McuCommand):
    NAME = "mcu"

    def __init__(self, sync_name="mcu"):
        super().__init__(sync_name)


class CommandServiceTest(unittest.TestCase):
    def setUp(self):
        self.states = []
        self.service = CommandService(lambda: "camera", lambda: "preview", on_state_changed=self.states.append)
        self.python_loader = FakeLoader(
            [
                FakeEntry("plain", PlainPython),
                FakeEntry("image_new", ImageNew),
                FakeEntry("image_old", ImageOld),
                FakeEntry("broken", error=SyntaxError("invalid syntax")),
            ]
        )
        self.mcu_loader = FakeLoader([FakeEntry("mcu", Mcu)])
        self.service.loaders = {"Python": self.python_loader, "Mcu": self.mcu_loader}
        self.service.commands = {"Python": self.python_loader.load(), "Mcu": self.mcu_loader.load()}
        Command.isPause = False

    def tearDown(self):
        Command.isPause = False

    def quiet(self):
        return contextlib.redirect_stdout(io.StringIO())

    # ---- 用意

    def test_assign_python_command(self):
        self.assertTrue(self.service.assign("Python", "plain"))
        self.assertIsInstance(self.service.current, PlainPython)
        self.assertIs(self.service.current_by_type["Python"], self.service.current)
        self.assertIsNone(self.service.current_by_type["Mcu"])
        self.assertTrue(self.service.can_pause)

    def test_assign_mcu_command_cannot_pause(self):
        self.assertTrue(self.service.assign("Mcu", "mcu"))
        self.assertIsInstance(self.service.current, Mcu)
        self.assertFalse(self.service.can_pause)

    def test_image_command_receives_camera_and_preview(self):
        self.service.assign("Python", "image_new")
        self.assertEqual(self.service.current.received, ("camera", "preview"))

    def test_old_style_image_command_receives_camera_only(self):
        self.service.assign("Python", "image_old")
        self.assertEqual(self.service.current.received, ("camera",))

    def test_needs_import_tells_whether_loading_will_take_time(self):
        # まだ読み込んでいないスクリプトは、用意するときに読み込みが起きる(重いスクリプトでは、画面が止まる)
        name = self.python_loader.entries[0].name
        module_name = self.python_loader.entries[0].module_name
        self.assertTrue(self.service.needs_import("Python", name))
        with mock.patch.dict(sys.modules, {module_name: object()}):
            self.assertFalse(self.service.needs_import("Python", name))
            # 読み込み直すときは、読み込み済みでも、読み込みが起きる
            self.assertTrue(self.service.needs_import("Python", name, reload=True))
        # 一覧にない名前、モジュールを持たない項目(実行リストなど)では、表示を出さない
        self.assertFalse(self.service.needs_import("Python", "no such command"))
        self.assertFalse(self.service.needs_import("Unknown", name))
        self.python_loader.entries[0].module_name = ""
        self.assertFalse(self.service.needs_import("Python", name))

    def test_assign_unknown_name_returns_false(self):
        with self.quiet():
            self.assertFalse(self.service.assign("Python", "no_such_command"))
        self.assertIsNone(self.service.current)

    def test_assign_broken_file_raises(self):
        with self.quiet(), self.assertRaises(CommandLoadError) as raised:
            self.service.assign("Python", "broken")
        self.assertEqual(raised.exception.entry.name, "broken")
        self.assertIsNone(self.service.current)

    def test_command_marked_as_not_pausable_cannot_pause(self):
        class NotPausable(PlainPython):
            CAN_PAUSE = False

        self.service.set_current("Python", NotPausable())
        self.assertFalse(self.service.can_pause)

    # ---- 追加の機能が足す読み込み先

    def test_extra_loaders_are_listed_after_the_commands(self):
        from unittest import mock

        from CommandLoader import CombinedLoader, CommandLoader

        extra_loader = FakeLoader([FakeEntry("extra", PlainPython)])
        service = CommandService(lambda: None, lambda: None)
        # 足していなければ、Python は「元の読み込み先 + 実行リスト」、Mcu は元のまま
        with mock.patch.object(command_service, "EXTRA_LOADERS", {"Python": [], "Mcu": []}):
            service.load()
        self.assertIsInstance(service.loaders["Python"], CombinedLoader)
        self.assertEqual(len(service.loaders["Python"].loaders), 2)
        self.assertIsInstance(service.loaders["Mcu"], CommandLoader)
        count = len(service.commands["Python"])
        with mock.patch.object(command_service, "EXTRA_LOADERS", {"Python": [lambda: extra_loader], "Mcu": []}):
            service.load()
        self.assertIsInstance(service.loaders["Python"], CombinedLoader)
        self.assertIsInstance(service.loaders["Mcu"], CommandLoader)
        names = [entry.name for entry in service.commands["Python"]]
        self.assertEqual((len(names), names[-1]), (count + 1, "extra"))
        self.assertNotIn("extra", [entry.name for entry in service.commands["Mcu"]])
        self.assertIs(service.find_class("Python", "extra"), PlainPython)
        service.reload()
        self.assertEqual(extra_loader.reload_count, 1)

    def test_reload_flag_is_passed_to_loader(self):
        self.service.assign("Python", "plain", reload=True)
        self.assertEqual(self.python_loader.loaded, [("plain", True)])

    def test_reload_refreshes_both_lists(self):
        self.service.reload()
        self.assertEqual((self.python_loader.reload_count, self.mcu_loader.reload_count), (1, 1))

    # ---- 実行

    def test_start_runs_command_and_records_output_page(self):
        command = RecordingCommand()
        self.service.set_current("Python", command)
        self.service.start("sender", output_page=2)
        self.assertEqual(command.calls, [("start", "sender")])
        self.assertEqual(Command.cur_command_name, "recording")
        self.assertEqual(Command.output_page, 2)
        self.assertEqual(self.states, [RUNNING])
        self.assertTrue(self.service.is_running)

    def test_command_finishing_by_itself_returns_to_idle(self):
        command = RecordingCommand()
        self.service.set_current("Python", command)
        self.service.start("sender", 0)
        command.post_process()
        self.assertEqual(self.states, [RUNNING, IDLE])
        self.assertFalse(self.service.is_running)

    def test_stop_waits_until_command_finishes(self):
        command = RecordingCommand()
        self.service.set_current("Python", command)
        self.service.start("sender", 0)
        self.service.stop("sender")
        self.assertEqual(command.calls, [("start", "sender"), ("end", "sender")])
        self.assertEqual(self.states, [RUNNING, STOPPING])
        self.assertTrue(self.service.is_running)
        command.post_process()
        self.assertEqual(self.states, [RUNNING, STOPPING, IDLE])

    def test_stop_of_command_that_finishes_inside_end(self):
        command = SynchronousCommand()
        self.service.set_current("Mcu", command)
        self.service.start("sender", 0)
        self.service.stop("sender")
        self.assertEqual(self.states, [RUNNING, STOPPING, IDLE])
        self.assertEqual(self.service.state, IDLE)

    def test_pause_resume_and_stop_clear_pause(self):
        command = RecordingCommand()
        self.service.set_current("Python", command)
        self.service.start("sender", 0)
        self.service.pause()
        self.assertTrue(Command.isPause)
        self.service.resume()
        self.assertFalse(Command.isPause)
        self.service.pause()
        self.service.stop("sender")
        self.assertFalse(Command.isPause)

    def test_service_does_not_import_tkinter(self):
        with io.open(command_service.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)
        self.assertNotIn("UiDispatcher", source)


if __name__ == "__main__":
    unittest.main()
