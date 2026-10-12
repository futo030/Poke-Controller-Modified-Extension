#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/tools_service.py のテスト(カメラを開かず、ファイルやフォルダを実際には開かずに実行できる)

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

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ControllerColors  # noqa: E402
import Profile  # noqa: E402
from services import tools_service  # noqa: E402
from services.tools_service import ToolError, ToolsService  # noqa: E402


def captured():
    out = io.StringIO()
    return contextlib.redirect_stdout(out), out


class FakeCamera:
    def __init__(self):
        self.capture_size = (1280, 720)
        self.image_bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.image_bgr[20, 10] = (1, 2, 3)  # B, G, R
        self.saved = []

    def saveCapture(self, filename=None, crop=None, crop_ax=None):
        self.saved.append((filename, crop, crop_ax))

    def readFrame(self):
        return self.image_bgr.copy()


class FakeLoader:
    def __init__(self, entries):
        self.entries = entries

    def findEntry(self, name):
        return self.entries.get(name)


class ToolsServiceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))
        self.command_path = os.path.join(self.directory, "command.py")
        with open(self.command_path, "w", encoding="utf-8") as file:
            file.write("# command\n")
        entry = SimpleNamespace(name="A", file_path=self.command_path)
        history = [{"class": "Python", "name": "A", "last_run": "x"}, {"class": "Mcu", "name": "M", "last_run": "y"}]
        self.topics = []
        self.core = SimpleNamespace(
            camera=FakeCamera(),
            profile="default",
            settings=SimpleNamespace(command_history=history, save=lambda: self.topics.append("saved")),
            commands=SimpleNamespace(
                loaders={"Python": FakeLoader({"A": entry, "Gone": SimpleNamespace(name="Gone", file_path="no such file.py")})},
                commands={"Python": [entry, SimpleNamespace(name="NoFile")], "Mcu": []},
                current=SimpleNamespace(NAME="Name", FILENAME="file.py", DEVELOPER="Dev"),
            ),
            _notify=self.topics.append,
        )
        self.tools = ToolsService(self.core)

    # ---------------------------------------------------------------- スクリーンショット

    def test_save_capture(self):
        camera = self.core.camera
        self.tools.save_capture()
        self.tools.save_capture([300, 200, 100, 50])  # 座標の大小は揃える
        self.tools.save_capture([-10, 0, 99999, 100], "sub/名前.png")
        self.assertEqual(camera.saved[0], (None, None, None))
        self.assertEqual(camera.saved[1], (None, 1, [100, 50, 300, 200]))
        filename, crop, area = camera.saved[2]
        self.assertEqual(filename, os.path.join(tools_service.TEMPLATE_DIR, "sub", "名前"))
        self.assertEqual((crop, area), (1, [0, 0, 1280, 100]))

    def test_bad_captures_are_refused(self):
        cases = (
            ([10, 10, 10, 50], None), (["a", 0, 1, 1], None), ([0, 0, 10], None),
            (None, "../outside"), (None, "a/../b"), (None, "C:/x"), (None, ""),
        )
        for area, name in cases:
            with self.assertRaises(ToolError, msg=(area, name)):
                self.tools.save_capture(area, name)
        self.core.camera.image_bgr = None
        with self.assertRaises(ToolError):
            self.tools.save_capture()
        self.assertEqual(self.core.camera.saved, [])

    def test_pixel_info(self):
        context, out = captured()
        with context:
            self.tools.pixel_info(10.7, 20)
            self.tools.pixel_info(5000, 5000)  # 画像の外は、座標だけを表示する
        expected = "Mouse down: Capture (10, 20)\nColor [R: 3, G: 2, B: 1]\nMouse down: Capture (5000, 5000)\n"
        self.assertEqual(out.getvalue(), expected)
        with self.assertRaises(ToolError):
            self.tools.pixel_info("a", 1)

    # ---------------------------------------------------------------- ファイルを開く

    def test_only_images_are_opened(self):
        image = os.path.join(self.directory, "shot.png")
        with open(image, "wb") as file:
            file.write(b"png")
        with mock.patch.object(tools_service, "open_with_system") as opened, mock.patch.object(
            tools_service, "open_folder"
        ) as folder:
            self.tools.open_image(image)
            self.tools.open_image(image, choose_app=True)
            self.tools.open_image_folder(image)
            for path in (self.command_path, os.path.join(self.directory, "none.png"), "C:\\Windows\\System32\\cmd.exe", ""):
                with self.assertRaises(ToolError, msg=path):
                    self.tools.open_image(path)
                with self.assertRaises(ToolError, msg=path):
                    self.tools.open_image_folder(path)
        self.assertEqual([call.args for call in opened.call_args_list], [(image, False), (image, True)])
        folder.assert_called_once_with(self.directory, select=image)

    def test_command_file(self):
        self.assertEqual(self.tools.command_file("py", "A"), os.path.abspath(self.command_path))
        for command_type, name in (("Python", "Unknown"), ("Python", "Gone"), ("Mcu", "A"), ("Other", "A")):
            with self.assertRaises(ToolError):
                self.tools.command_file(command_type, name)
        with mock.patch.object(tools_service.util, "open_text_file") as text, mock.patch.object(
            tools_service, "open_with_system"
        ) as system, mock.patch.object(tools_service, "open_folder") as folder:
            self.tools.open_command_file("Python", "A")
            self.tools.open_command_file("Python", "A", "with")
            self.tools.open_command_file("Python", "A", "folder")
        text.assert_called_once_with(os.path.abspath(self.command_path))
        system.assert_called_once_with(os.path.abspath(self.command_path), choose_app=True)
        folder.assert_called_once()

    def test_command_mtimes(self):
        mtimes = self.tools.command_mtimes()
        self.assertGreater(mtimes["Python"]["A"], 0)
        self.assertEqual(mtimes["Python"]["NoFile"], 0.0)
        json.dumps(self.tools.state())

    # ---------------------------------------------------------------- 実行履歴

    def test_history(self):
        self.tools.delete_history("Python", "A")
        self.assertEqual([h["name"] for h in self.core.settings.command_history], ["M"])
        with self.assertRaises(ToolError):
            self.tools.delete_history("Python", "A")
        self.tools.clear_history()
        self.assertEqual(self.core.settings.command_history, [])
        self.assertEqual(self.topics, ["saved", "command", "saved", "command"])

    # ---------------------------------------------------------------- プリセット・プロファイル

    def test_color_preset(self):
        with mock.patch.object(ControllerColors, "USER_PRESET_DIR", os.path.join(self.directory, "colors")):
            context, _ = captured()
            with context:
                self.tools.save_color_preset("GameCube", "mine")
            self.assertEqual([name for name, _ in ControllerColors.list_user_presets("GameCube")], ["mine"])
            for controller, name in (("PlayStation", "x"), ("GameCube", "../x"), ("GameCube", "a/b"), ("GameCube", "")):
                with self.assertRaises(ToolError):
                    self.tools.save_color_preset(controller, name)

    def test_add_profile(self):
        kinds = []
        with mock.patch.object(
            Profile, "check_profile_name", lambda name: None if name == "new" else "bad name"
        ), mock.patch.object(Profile, "create_profile_bat", lambda name, kind=None: kinds.append(kind) or "new.bat"), mock.patch.object(
            Profile, "add_profile_priority"
        ) as priority, mock.patch.object(tools_service.shutil, "copytree") as copy:
            context, _ = captured()
            with context:
                message = self.tools.add_profile(" new ", True)
                self.tools.add_profile("new", False, Profile.BAT_CLASSIC)
            with self.assertRaises(ToolError):
                self.tools.add_profile("bad", True)
        self.assertIn("--profile new", message)
        self.assertIn("new.bat", message)
        copy.assert_called_once()
        self.assertTrue(copy.call_args.args[0].endswith(os.path.join("profiles", "default")))
        priority.assert_called_once_with("new")
        # 起動用の bat の形は、指定があれば、そのまま渡す
        self.assertEqual(kinds, [None, Profile.BAT_CLASSIC])
        self.assertIn("uv_environment", self.tools.state())

    # ---------------------------------------------------------------- ヘルプ

    def test_help_texts(self):
        # 環境の診断(以前の Version確認 の内容を含む: アプリ・OS・Python・ライブラリの版)
        context = self.tools.diagnostics_context()
        self.assertEqual((context["profile"], context["command_counts"]), ("default", {"Python": 2, "Mcu": 0}))
        self.assertIs(context["serial_connected"], False)
        text = self.tools.diagnostics_text()
        self.assertIn("] Python: ", text)
        self.assertIn("] OS: ", text)
        self.assertIn("pyserial ", text)
        self.assertIn("pynput ", text)  # "pynput>=1.7.7" は、名前の部分だけを使う
        self.assertNotIn("pynput>=", text)
        self.assertIn("プロファイル: default", text)
        self.assertFalse(hasattr(self.tools, "version_text"))
        plain, masked = self.tools.diagnostics_texts()
        self.assertEqual(len(plain.splitlines()), len(masked.splitlines()))
        self.assertIn("***", masked)
        self.assertIn("ver.", self.tools.changelog_text())
        self.assertTrue(self.tools.license_text().strip())

    def test_question(self):
        self.assertEqual(self.tools.question_defaults()["program"], "Name (file.py)")
        self.assertEqual(self.tools.question_defaults()["developer"], "Dev")
        context, out = captured()
        with context:
            text = self.tools.question_text("P", "D", "Q", "T")
        self.assertIn("■質問内容(詳しくご記述ください。)\nQ\n", text)
        self.assertEqual(out.getvalue().strip(), text)
        with self.assertRaises(ToolError):
            self.tools.question_text("P", "D", " ", "T")

    def test_windows_notification(self):
        sent = []
        fake = SimpleNamespace(notification=SimpleNamespace(notify=lambda **kwargs: sent.append(kwargs)))
        with mock.patch.dict(sys.modules, {"plyer": fake}):
            context, _ = captured()
            with context:
                self.tools.send_windows_notification()
        self.assertEqual((sent[0]["message"], sent[0]["timeout"]), ("Notification Test", 5))
        self.assertIn("(profile:default)", sent[0]["title"])
        with mock.patch.dict(sys.modules, {"plyer": None}), self.assertRaises(ToolError):
            self.tools.send_windows_notification()

    def test_introduction_at_startup(self):
        from services import introduction_store

        with mock.patch.object(Profile, "PROFILES_DIR", self.directory):
            self.assertTrue(self.tools.state()["show_introduction"])
            self.tools.set_introduction_hidden(True)
            self.assertFalse(self.tools.state()["show_introduction"])
            # Web 版の紹介文についての設定として保存する(ウィンドウの画面の設定とは別)
            web = introduction_store.WEB
            self.assertEqual(introduction_store.hidden_revision(web), introduction_store.content_revision(web))
            self.assertIsNone(introduction_store.hidden_revision())
            self.assertTrue(introduction_store.should_show_at_startup())
            self.tools.set_introduction_hidden(False)
            self.assertTrue(self.tools.state()["show_introduction"])
        self.assertEqual(self.topics, ["settings", "settings"])

    def test_introduction_kinds_are_kept_separately(self):
        from services import introduction_store as store

        self.assertGreater(len(store.load_pages(store.WEB)), 0)
        self.assertNotEqual(store.load_pages()[0].title, store.load_pages(store.WEB)[0].title)
        self.assertNotEqual(store.content_revision(), store.content_revision(store.WEB))
        with mock.patch.object(Profile, "PROFILES_DIR", self.directory):
            store.set_hidden(True)
            store.set_hidden(True, store.WEB)
            self.assertFalse(store.should_show_at_startup())
            self.assertFalse(store.should_show_at_startup(store.WEB))
            # 一方を戻しても、もう一方は残る
            store.set_hidden(False, store.WEB)
            self.assertFalse(store.should_show_at_startup())
            self.assertTrue(store.should_show_at_startup(store.WEB))
            store.set_hidden(True, store.WEB)
            store.set_hidden(False)
            self.assertTrue(store.should_show_at_startup())
            self.assertFalse(store.should_show_at_startup(store.WEB))
            # これまでの形式(項目が1つだけ)のファイルも読める
            with open(os.path.join(self.directory, store.STATE_FILE), "w", encoding="utf-8") as file:
                json.dump({"hidden_revision": store.content_revision()}, file)
            self.assertFalse(store.should_show_at_startup())
            self.assertTrue(store.should_show_at_startup(store.WEB))
            with open(os.path.join(self.directory, store.STATE_FILE), "w", encoding="utf-8") as file:
                file.write("[1, 2]")
            self.assertTrue(store.should_show_at_startup())

    def test_update_check_reports_the_result(self):
        # 通信はしない(確認の処理そのものは、test_update_check.py)
        update_check = tools_service.update_check
        for result, expected in ((update_check.UpdateCheckError("no network"), "-1"), ([None], "0")):
            with mock.patch.object(update_check, "find_update", side_effect=result):
                context, _ = captured()
                with context:
                    self.assertEqual(self.tools.check_update(), expected)

    def test_relative_names(self):
        self.assertEqual(tools_service.check_relative_name(" a\\b / c.PNG "), "a/b/c")
        for name in ("", "..", "a/../b", "a//b", "a:b", "a\nb", "/a"):
            with self.assertRaises(ToolError, msg=name):
                tools_service.check_relative_name(name)

    def test_module_does_not_import_tkinter(self):
        with io.open(tools_service.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)


if __name__ == "__main__":
    unittest.main()
