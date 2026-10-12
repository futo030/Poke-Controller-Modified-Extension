#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/app_core.py のテスト(画面を起動せず、カメラもシリアルも開かずに実行できる)

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
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Profile  # noqa: E402
from Commands.CommandBase import Command  # noqa: E402
from Commands.Keys import Direction, Stick, Touchscreen  # noqa: E402
from services import app_core, command_service  # noqa: E402
from services.app_core import AppCore  # noqa: E402
from services.settings_store import AppSettings  # noqa: E402


class FakeKeys:
    def __init__(self):
        self.calls = []

    def input(self, value):
        self.calls.append(("input", value))

    def inputEnd(self, value):
        self.calls.append(("inputEnd", value))

    def init_hat(self):
        self.calls.append(("init_hat",))


class FakeCommands:
    """コマンドを実際には動かさない CommandService の代役"""

    def __init__(self):
        self.state = command_service.IDLE
        self.commands = {"Python": [SimpleNamespace(name="A", tags=["t"])], "Mcu": [SimpleNamespace(name="M", tags=[])]}
        self.current = None
        self.can_pause = True
        self.calls = []

    @property
    def is_running(self):
        return self.state != command_service.IDLE

    def assign(self, command_type, name, reload=False):
        self.current = SimpleNamespace(NAME=name)
        self.calls.append(("assign", command_type, name))
        return True

    def record_usage(self, command_type, name):
        self.calls.append(("record_usage", command_type, name))

    def start(self, sender, page):
        self.state = command_service.RUNNING
        self.calls.append(("start", page))

    def stop(self, sender):
        self.state = command_service.STOPPING
        self.calls.append(("stop",))

    def pause(self):
        Command.isPause = True

    def resume(self):
        Command.isPause = False


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class AppCoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.original_path = AppSettings.SETTING_PATH
        AppSettings.SETTING_PATH = os.path.join(self.directory, "settings.ini")
        self.saved = {name: getattr(Command, name) for name in ("app_name", "profilename", "isPause")}
        patcher = mock.patch.object(app_core, "apply_profile", lambda profile: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.cleanup)
        self.core = AppCore("test")
        self.keys = self.core.mouse_keys = FakeKeys()
        self.commands = self.core.commands = FakeCommands()
        self.core.record._is_command_running = lambda: self.commands.is_running

    def cleanup(self):
        AppSettings.SETTING_PATH = self.original_path
        for name, value in self.saved.items():
            setattr(Command, name, value)
        Profile.set_read_only(False)
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_state_can_be_sent_as_json(self):
        state = self.core.state()
        json.dumps(state)
        self.assertEqual(state["profile"], "test")
        self.assertEqual(state["command"], {"state": "idle", "paused": False, "can_pause": False, "name": ""})
        self.assertEqual(state["commands"]["Python"], [{"name": "A", "tags": ["t"]}])
        self.assertFalse(state["serial"]["connected"])
        # Status の欄: 何もつながっていないとき
        self.assertEqual(list(state["status"]), ["camera", "audio_input", "audio_output", "serial", "command", "started"])
        self.assertEqual((state["status"]["camera"], state["status"]["serial"], state["status"]["command"]),
                         ("(開いていません)", "(接続していません)", "(なし)"))

    def test_start_command(self):
        topics = []
        self.core.add_listener(topics.append)
        with quiet():
            self.assertTrue(self.core.start_command("py", "A"))
        self.assertEqual(
            self.commands.calls, [("assign", "Python", "A"), ("record_usage", "Python", "A"), ("start", 0)]
        )
        self.assertEqual([(h["class"], h["name"]) for h in self.core.settings.command_history], [("Python", "A")])
        self.assertEqual(self.core.state()["command"]["name"], "A")
        # Status の欄には、実行中のコマンドの名前と、開始した時刻が、別の行で出る
        self.assertEqual(self.core.state()["status"]["command"], "A")
        from datetime import datetime

        self.commands.started_at = datetime(2026, 10, 12, 8, 30, 0)
        self.assertEqual(self.core.state()["status"]["command"], "A")
        self.assertEqual(self.core.state()["status"]["started"], "2026/10/12 08:30:00")

    def test_unknown_command_is_not_started(self):
        with quiet():
            self.assertFalse(self.core.start_command("Python", "no such command"))
            self.assertFalse(self.core.start_command("Other", "A"))
        self.assertEqual(self.commands.calls, [])

    def test_command_is_not_started_twice(self):
        with quiet():
            self.core.start_command("Python", "A")
            self.assertFalse(self.core.start_command("Mcu", "M"))
        self.assertEqual([call[0] for call in self.commands.calls], ["assign", "record_usage", "start"])

    def test_command_is_not_started_while_recording(self):
        with mock.patch.object(type(self.core.record), "is_recording", lambda self: True), quiet():
            self.assertFalse(self.core.start_command("Python", "A"))
        self.assertEqual(self.commands.calls, [])

    def test_stop_pause_resume(self):
        with quiet():
            self.core.stop_command()  # 実行していない場合は何もしない
            self.assertEqual(self.commands.calls, [])
            self.core.start_command("Python", "A")
            self.core.pause_command()
            self.assertTrue(self.core.state()["command"]["paused"])
            self.core.resume_command()
            self.assertFalse(self.core.state()["command"]["paused"])
            self.core.stop_command()
            self.core.stop_command()  # 停止を待っている間は、もう一度頼まない
        self.assertEqual([call[0] for call in self.commands.calls], ["assign", "record_usage", "start", "stop"])

    def test_stick_values(self):
        with quiet():
            self.core.move_stick("left", 0, 1)
            self.core.move_stick("left", 90, 1)
            self.core.move_stick("right", 180, 0.5)
            self.core.move_stick("right", 0, 5)  # 大きさは 1 までに収める
            self.core.release_stick("left")
        # (値の求め方は、tkinter 版のプレビュー上のマウス操作と同じ)
        values = [(call[1].stick, (call[1].x, call[1].y)) for call in self.keys.calls]
        self.assertEqual(
            values,
            [
                (Stick.LEFT, (255, 127)),
                (Stick.LEFT, (128, 255)),
                (Stick.RIGHT, (64, 128)),
                (Stick.RIGHT, (255, 127)),
                (Stick.LEFT, (128, 127)),
            ],
        )
        self.assertTrue(all(isinstance(call[1], Direction) for call in self.keys.calls))

    def test_touch_is_mapped_into_the_touchscreen_area(self):
        self.core.settings.touchscreen_ratio = "0.25,0.5,0.75,1.0"
        self.assertTrue(self.core.touch(0.5, 0.75))
        self.assertFalse(self.core.touch(0.1, 0.75))  # 範囲の外
        self.assertFalse(self.core.touch(0.5, 0.4))
        self.core.release_touch()
        (kind, touch), (end_kind, end_touch) = self.keys.calls
        self.assertIsInstance(touch, Touchscreen)
        self.assertEqual((kind, touch.x, touch.y), ("input", 160, 120))
        self.assertEqual((end_kind, end_touch.x, end_touch.y), ("inputEnd", 0, 0))

    def test_touchscreen_ratio_falls_back_to_the_saved_area(self):
        settings = self.core.settings
        settings.touchscreen_ratio = ""
        settings.show_size = "640x360"
        settings.touchscreen_start_x, settings.touchscreen_start_y = 64, 180
        settings.touchscreen_end_x, settings.touchscreen_end_y = 576, 360
        self.assertEqual(self.core.touchscreen_ratio(), (0.1, 0.5, 0.9, 1.0))
        settings.show_size = ""
        self.assertIsNone(self.core.touchscreen_ratio())

    def test_touchscreen_formats(self):
        for name, expected in (("Default", False), ("Qingpi", True), ("3DS Controller", True), ("3DS Controller(FW:x.4-)", True)):
            self.core.settings.serial_data_format_name = name
            self.assertEqual(self.core.has_touchscreen, expected, name)

    def test_keyboard_needs_a_connection(self):
        # シリアルに接続していない間は、キーボードの受け付けを始めない
        self.assertFalse(self.core.set_keyboard_active(True))
        self.assertFalse(self.core.set_keyboard_active(False))

    def test_module_does_not_import_tkinter(self):
        with io.open(app_core.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)


class ProfilePathsTest(unittest.TestCase):
    """プロファイルごとの設定ファイルの場所(services/profile_paths.py)"""

    TARGETS = (
        ("services.settings_store", "AppSettings", "SETTING_PATH"),
        ("LineNotify", "Line_Notify", "LINE_TOKEN_PATH"),
        ("DiscordNotify", "Discord_Notify", "DISCORD_SETTING_PATH"),
        ("ExternalTools", "SocketCommunications", "SOCKET_TOKEN_PATH"),
        ("ExternalTools", "MQTTCommunications", "MQTT_TOKEN_PATH"),
        ("Keyboard", "SwitchKeyboardController", "SETTING_PATH"),
    )

    def setUp(self):
        import importlib

        self.classes = [(getattr(importlib.import_module(module), name), attribute) for module, name, attribute in self.TARGETS]
        self.saved = [getattr(cls, attribute) for cls, attribute in self.classes]
        self.directory = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.directory)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        os.chdir(self.cwd)
        for (cls, attribute), value in zip(self.classes, self.saved):
            setattr(cls, attribute, value)
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_default_profile_keeps_the_paths(self):
        from services import profile_paths

        with mock.patch.object(Profile, "add_profile_priority") as added:
            self.assertIsNone(profile_paths.apply_profile("default"))
        self.assertEqual([getattr(cls, attribute) for cls, attribute in self.classes], self.saved)
        self.assertTrue(os.path.isdir(os.path.join("profiles", "default")))
        added.assert_called_once_with("default")

    def test_other_profile_switches_every_setting_file(self):
        from services import profile_paths

        folder = os.path.join(profile_paths.SERIAL_CONTROLLER_DIR, "profiles", "sub")
        with mock.patch.object(Profile, "add_profile_priority") as added:
            self.assertEqual(profile_paths.apply_profile("sub"), os.path.join(folder, "settings.ini"))
            profile_paths.apply_profile("sub")  # フォルダがある場合は、優先度に足さない
        added.assert_called_once_with("sub")
        expected = ["settings.ini", "line_token.ini", "discord_token.ini", "external_token.ini", "external_token.ini", "settings.ini"]
        self.assertEqual(
            [getattr(cls, attribute) for cls, attribute in self.classes], [os.path.join(folder, name) for name in expected]
        )


if __name__ == "__main__":
    unittest.main()
