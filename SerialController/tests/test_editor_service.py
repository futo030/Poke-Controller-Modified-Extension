#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/editor_service.py のテスト(画面を起動せず、設定ファイルは一時フォルダのものを使う)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import configparser
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

import ControllerColors  # noqa: E402
import KeyMap  # noqa: E402
import Profile  # noqa: E402
from DiscordNotify import Discord_Notify  # noqa: E402
from LineNotify import Line_Notify  # noqa: E402
from Mask import Mask  # noqa: E402
from services import editor_service  # noqa: E402
from services.editor_service import EditError, EditorService  # noqa: E402
from services.settings_store import AppSettings  # noqa: E402


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class FakeCore:
    def __init__(self):
        self.settings = AppSettings()
        self.masks = []
        self.camera = SimpleNamespace(capture_size=(1280, 720), capture_filter=None)
        self.keyboard = None
        self.calls = []
        self.topics = []
        self.names = {"Python": ["A", "B"], "Mcu": ["M"]}

    def command_names(self, command_type):
        return self.names[command_type]

    def start_command(self, command_type, name):
        self.calls.append(("start", command_type, name))
        return True

    def keyboard_console(self):
        return KeyMap.console_of_layout(self.settings.software_controller_layout)

    def touchscreen_ratio(self):
        from services import geometry

        return geometry.parse_ratio(self.settings.touchscreen_ratio)

    def set_softcon_layout(self, name, color_settings=None):
        self.calls.append(("layout", name))

    def set_simulator_layout(self, name):
        self.calls.append(("simulator", name))

    def _notify(self, topic):
        self.topics.append(topic)


class EditorServiceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.saved = {
            (AppSettings, "SETTING_PATH"): AppSettings.SETTING_PATH,
            (Discord_Notify, "DISCORD_SETTING_PATH"): Discord_Notify.DISCORD_SETTING_PATH,
            (Line_Notify, "LINE_TOKEN_PATH"): Line_Notify.LINE_TOKEN_PATH,
            (editor_service, "MASK_DIR"): editor_service.MASK_DIR,
        }
        AppSettings.SETTING_PATH = os.path.join(self.directory, "settings.ini")
        Discord_Notify.DISCORD_SETTING_PATH = os.path.join(self.directory, "discord_token.ini")
        Line_Notify.LINE_TOKEN_PATH = os.path.join(self.directory, "line_token.ini")
        editor_service.MASK_DIR = os.path.join(self.directory, "Masks")
        self.saved_colors = ControllerColors.settings_texts()
        self.saved_session = dict(KeyMap._session_keymaps)
        self.addCleanup(self.cleanup)
        self.core = FakeCore()
        self.editor = EditorService(self.core)

    def cleanup(self):
        for (target, name), value in self.saved.items():
            setattr(target, name, value)
        ControllerColors.load_settings(self.saved_colors)
        KeyMap._session_keymaps.clear()
        KeyMap._session_keymaps.update(self.saved_session)
        Profile.set_read_only(False)
        shutil.rmtree(self.directory, ignore_errors=True)

    def reload_settings(self) -> AppSettings:
        return AppSettings()

    # ---------------------------------------------------------------- ショートカット

    def test_shortcuts(self):
        self.assertEqual(len(self.editor.shortcuts()), 12)
        self.assertEqual(self.editor.shortcuts()[0], {"num": 1, "class": "None", "name": "(empty)"})
        self.editor.set_shortcut(3, "py", "B")
        self.editor.set_shortcut("12", "MCU", "M")
        self.assertEqual(self.editor.shortcuts()[2], {"num": 3, "class": "Python", "name": "B"})
        loaded = self.reload_settings()
        self.assertEqual((loaded.command_class_dict["12"], loaded.command_name_dict["12"]), ("Mcu", "M"))
        self.assertTrue(self.editor.start_shortcut(3))
        self.assertEqual(self.core.calls, [("start", "Python", "B")])
        self.editor.clear_shortcut(3)
        with quiet():
            self.assertFalse(self.editor.start_shortcut(3))
        self.assertEqual(len(self.core.calls), 1)

    def test_bad_shortcuts_are_refused(self):
        for call in (
            lambda: self.editor.set_shortcut(0, "Python", "A"),
            lambda: self.editor.set_shortcut(13, "Python", "A"),
            lambda: self.editor.set_shortcut("x", "Python", "A"),
            lambda: self.editor.set_shortcut(1, "Python", "no such command"),
            lambda: self.editor.set_shortcut(1, "Other", "A"),
            lambda: self.editor.start_shortcut(99),
        ):
            with self.assertRaises(EditError):
                call()
        self.assertEqual(self.editor.shortcuts()[0]["class"], "None")

    # ---------------------------------------------------------------- 目隠し

    def test_masks(self):
        self.editor.add_mask("Rectangle", 300, 200, 100, 50)  # 座標の大小は揃える
        self.editor.add_mask("Ellipse", -50, 600, 5000, 900)  # カメラ画像の範囲に収める
        state = self.editor.masks_state()
        json.dumps(state)
        self.assertEqual(state["items"][0], {"shape": "Rectangle", "x1": 100, "y1": 50, "x2": 300, "y2": 200, "color": "#000000", "enabled": True})
        self.assertEqual([state["items"][1][k] for k in ("x1", "y1", "x2", "y2")], [0, 600, 1280, 720])
        self.editor.update_mask(0, {"x2": 400, "color": "#FF0000", "enabled": False, "shape": "Ellipse"})
        mask = self.core.masks[0]
        self.assertEqual((mask.shape, mask.x2, mask.color, mask.enabled), ("Ellipse", 400, "#ff0000", False))
        self.assertEqual(self.reload_settings().masks, [m.to_text() for m in self.core.masks])
        self.editor.delete_mask(0)
        self.assertEqual(len(self.core.masks), 1)

    def test_bad_masks_are_refused(self):
        self.editor.add_mask("Rectangle", 10, 10, 100, 100)
        for call in (
            lambda: self.editor.add_mask("Star", 0, 0, 10, 10),
            lambda: self.editor.add_mask("Rectangle", 10, 10, 11, 100),
            lambda: self.editor.add_mask("Rectangle", "a", 0, 10, 10),
            lambda: self.editor.add_mask("Rectangle", 2000, 0, 3000, 10),
            lambda: self.editor.update_mask(5, {"enabled": False}),
            lambda: self.editor.update_mask(0, {"color": "red; x"}),
            lambda: self.editor.update_mask(0, {"x1": 100, "x2": 100}),
            lambda: self.editor.delete_mask(-1),
        ):
            with self.assertRaises(EditError):
                call()
        self.assertEqual(self.core.masks, [Mask("Rectangle", 10, 10, 100, 100, "#000000", True)])

    def test_masks_are_applied_to_captures_only_when_asked(self):
        self.editor.add_mask("Rectangle", 10, 10, 100, 100)
        self.assertIsNone(self.core.camera.capture_filter)
        self.editor.set_mask_options(apply_to_capture=True)
        self.assertIsNotNone(self.core.camera.capture_filter)
        self.editor.set_mask_options(show=False)
        self.assertIsNone(self.core.camera.capture_filter)
        loaded = self.reload_settings()
        self.assertEqual((loaded.is_show_mask, loaded.is_mask_apply_to_capture), (False, True))

    def test_mask_files(self):
        with self.assertRaises(EditError):
            self.editor.save_mask_file("empty")
        self.editor.add_mask("Rectangle", 10, 10, 100, 100)
        with quiet():
            self.editor.save_mask_file(" one.json ")
            self.editor.add_mask("Ellipse", 0, 0, 50, 50)
            self.editor.save_mask_file("two")
            self.assertEqual(self.editor.mask_files(), ["one", "two"])
            self.editor.load_mask_file("one", replace=False)
            self.assertEqual(len(self.core.masks), 3)
            self.editor.load_mask_file("one", replace=True)
        self.assertEqual(self.core.masks, [Mask("Rectangle", 10, 10, 100, 100, "#000000", True)])

    def test_mask_files_stay_in_the_mask_folder(self):
        self.editor.add_mask("Rectangle", 10, 10, 100, 100)
        for name in ("../outside", "..\\outside", "C:\\temp\\a", "a/b", "", "..", "a:b"):
            with self.assertRaises(EditError, msg=name):
                self.editor.save_mask_file(name)
            with self.assertRaises(EditError, msg=name):
                self.editor.load_mask_file(name, True)
        with self.assertRaises(EditError):
            self.editor.load_mask_file("no such file", True)
        self.assertFalse(os.path.exists(os.path.join(self.directory, "outside.json")))

    # ---------------------------------------------------------------- タッチスクリーン

    def test_touchscreen_area(self):
        self.core.settings.show_size = "640x360"
        with quiet():
            self.editor.set_touchscreen_area(128, 360, 1152, 720)
        self.assertEqual(self.editor.touchscreen_area(), [128, 360, 1152, 720])
        loaded = self.reload_settings()
        self.assertEqual(loaded.touchscreen_ratio, "0.1,0.5,0.9,1.0")
        # これまでのウィンドウの画面が使う、プレビュー上の座標も同じ範囲にする
        self.assertEqual(
            (loaded.touchscreen_start_x, loaded.touchscreen_start_y, loaded.touchscreen_end_x, loaded.touchscreen_end_y),
            (64, 180, 576, 360),
        )
        with quiet():
            self.editor.set_touchscreen_area(-10, 0, 99999, 100)
        self.assertEqual(self.editor.touchscreen_area(), [0, 0, 1280, 100])

    def test_bad_touchscreen_area_is_refused(self):
        for values in ((100, 100, 100, 200), (300, 100, 200, 200), ("a", 0, 1, 1), (2000, 0, 3000, 10)):
            with self.assertRaises(EditError):
                self.editor.set_touchscreen_area(*values)

    # ---------------------------------------------------------------- キーコンフィグ

    def test_valid_keys(self):
        for key in ("a", "A", "1", ";", "Key.space", "Key.up", "Key.shift_r", "10000"):
            self.assertTrue(editor_service.is_valid_key(key), key)
        for key in ("", "ab", "Key.", "Key.no_such_key", "__import__('os')", "Key.space; 1", None, 5, "Key.space\n"):
            self.assertFalse(editor_service.is_valid_key(key), repr(key))

    def test_keymaps(self):
        state = self.editor.keymaps()
        json.dumps(state)
        self.assertEqual(state["consoles"], ["Switch", "3DS", "DS", "GameCube"])
        self.assertEqual(state["current"], "Switch")
        self.assertEqual(state["keymaps"]["Switch"]["Button.A"], "a")
        self.assertEqual(state["buttons"]["3DS"][0][0], ["L", "Button.L"])
        with quiet():
            self.editor.save_keymaps({"Switch": {"Button.A": "z", "Hat.TOP": "Key.up"}, "3DS": {"Button.A": "Key.space"}})
        state = self.editor.keymaps()
        self.assertEqual((state["keymaps"]["Switch"]["Button.A"], state["keymaps"]["Switch"]["Hat.TOP"]), ("z", "Key.up"))
        self.assertEqual(state["keymaps"]["3DS"]["Button.A"], "Key.space")
        self.assertEqual(state["keymaps"]["DS"]["Button.A"], "a")
        # ほかの設定を保存しても、キーの対応は残る
        self.core.settings.save()
        self.assertEqual(self.editor.keymaps()["keymaps"]["Switch"]["Button.A"], "z")

    def test_bad_keymaps_are_refused(self):
        before = self.editor.keymaps()["keymaps"]
        for keymaps in (
            {"Switch": {"Button.A": "__import__('os').system('x')"}},
            {"Switch": {"Button.A": "b"}},  # B と同じキー
            {"3DS": {"Hat.TOP": "Key.up", "Hat.BTM": "Key.up"}},
            "not a dict",
        ):
            with self.assertRaises(EditError):
                self.editor.save_keymaps(keymaps)
        self.assertEqual(self.editor.keymaps()["keymaps"], before)

    def test_keymaps_are_kept_only_in_memory_for_a_read_only_profile(self):
        with io.open(AppSettings.SETTING_PATH, encoding="utf-8") as file:
            before = file.read()
        Profile.set_read_only(True)
        with quiet():
            self.editor.save_keymaps({"Switch": {"Button.A": "z"}})
        with io.open(AppSettings.SETTING_PATH, encoding="utf-8") as file:
            self.assertEqual(file.read(), before)
        self.assertEqual(self.editor.keymaps()["keymaps"]["Switch"]["Button.A"], "z")

    def test_saving_reloads_the_keyboard(self):
        calls = []
        self.core.keyboard = SimpleNamespace(reloadKeyMap=calls.append)
        with quiet():
            self.editor.save_keymaps({})
        self.assertEqual(calls, ["Switch"])

    # ---------------------------------------------------------------- 本体の色

    def test_controller_colors(self):
        state = self.editor.colors_state()
        json.dumps(state)
        joycon = state["types"][0]
        self.assertEqual((joycon["name"], joycon["keys"]), ("Switch (Joy-Con)", [["left", "Left"], ["right", "Right"]]))
        self.assertEqual(joycon["presets"][0]["name"], "Default")
        self.editor.set_controller_colors("Switch (Joy-Con)", {"left": "#112233"})
        colors = ControllerColors.get_colors("Switch (Joy-Con)")
        self.assertEqual(colors["left"].lower(), "#112233")
        self.assertEqual(colors["right"], joycon["colors"]["right"])
        # 表示中の Software-Controller と Controller Simulator を、新しい色で作り直す
        settings = self.core.settings
        self.assertEqual(self.core.calls, [("layout", settings.software_controller_layout), ("simulator", settings.controller_layout)])
        self.assertIn("#112233", self.reload_settings().controller_colors["switch_joycon"].lower())

    def test_bad_colors_are_refused(self):
        for controller, colors in (("PlayStation", {"body": "#000000"}), ("GameCube", {"body": "purple"}), ("GameCube", "x")):
            with self.assertRaises(EditError):
                self.editor.set_controller_colors(controller, colors)

    # ---------------------------------------------------------------- 通知先

    def test_discord_destinations(self):
        state = self.editor.discord_state()
        self.assertEqual((state["names"], state["selected"], state["default_set"]), ([], "DISCORD_WEBHOOK", False))
        with quiet():
            # 既定の通知先が未設定の間は、名前を変えられない(既定の通知先として保存する)
            state = self.editor.save_discord("OTHER", {"webhook_url": " https://example.invalid/hook1 ", "username": "bot"})
        self.assertEqual((state["names"], state["selected"], state["default_set"]), (["DISCORD_WEBHOOK"], "DISCORD_WEBHOOK", True))
        self.assertEqual(state["values"], {"webhook_url": "https://example.invalid/hook1", "username": "bot", "avatar_url": ""})
        self.assertEqual(self.editor.discord_state()["selected"], "DISCORD_WEBHOOK1")
        with quiet():
            state = self.editor.save_discord("SUB", {"webhook_url": "https://example.invalid/hook2"})
        self.assertEqual(state["names"], ["DISCORD_WEBHOOK", "SUB"])
        self.assertEqual(self.editor.discord_state("SUB")["values"]["webhook_url"], "https://example.invalid/hook2")
        setting = configparser.ConfigParser()
        setting.read(Discord_Notify.DISCORD_SETTING_PATH, encoding="utf-8")
        self.assertEqual(setting.sections(), ["DISCORD", "DISCORD_WEBHOOK", "SUB"])
        with quiet():
            state = self.editor.delete_discord("SUB")
        self.assertEqual(state["names"], ["DISCORD_WEBHOOK"])

    def test_bad_discord_destinations_are_refused(self):
        with quiet():
            self.editor.save_discord("DISCORD_WEBHOOK", {"webhook_url": "https://example.invalid/hook"})
        for call in (
            lambda: self.editor.save_discord("", {"webhook_url": "https://example.invalid/x"}),
            lambda: self.editor.save_discord("DISCORD", {"webhook_url": "https://example.invalid/x"}),
            lambda: self.editor.save_discord("a]b", {"webhook_url": "https://example.invalid/x"}),
            lambda: self.editor.save_discord("NEW", {"webhook_url": "  "}),
            lambda: self.editor.save_discord("NEW", None),
            lambda: self.editor.delete_discord("DISCORD_WEBHOOK"),
            lambda: self.editor.delete_discord("no such name"),
        ):
            with self.assertRaises(EditError):
                call()
        self.assertEqual(self.editor.discord_state()["names"], ["DISCORD_WEBHOOK"])

    def test_line_token(self):
        self.assertFalse(self.editor.line_token_is_set())
        with self.assertRaises(EditError):
            self.editor.save_line_token("  ")
        with quiet():
            self.editor.save_line_token(" dummy-token ")
        self.assertTrue(self.editor.line_token_is_set())
        setting = configparser.ConfigParser()
        setting.read(Line_Notify.LINE_TOKEN_PATH, encoding="utf-8")
        self.assertEqual(setting["LINE"]["token"], "dummy-token")

    def test_module_does_not_import_tkinter(self):
        with io.open(editor_service.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)


class FileNameTest(unittest.TestCase):
    def test_check_file_name(self):
        self.assertEqual(editor_service.check_file_name(" name.JSON "), "name")
        self.assertEqual(editor_service.check_file_name("目隠し 1"), "目隠し 1")
        with mock.patch.object(editor_service, "MASK_DIR", "x"):
            for name in ("a/b", "a\\b", "..", "", "a?b", "a\nb"):
                with self.assertRaises(EditError):
                    editor_service.check_file_name(name)


if __name__ == "__main__":
    unittest.main()
