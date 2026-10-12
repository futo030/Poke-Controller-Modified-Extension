#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord の通知に付ける画像(画面 / ウィンドウ全体)のテスト(画面を起動せず、通信もしない)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import configparser
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import WindowCapture  # noqa: E402
from Commands.CommandBase import Command  # noqa: E402
from Commands.PythonCommandBase import PythonCommand  # noqa: E402
from services import notification_image  # noqa: E402
from services.settings_store import AppSettings  # noqa: E402


def setUpModule():
    """通知のクラスを代役にする(コマンドを作るたびに、本物の通知先へ接続を確かめに行かないようにする)"""
    for name in ("Line_Notify", "Discord_Notify"):
        patcher = mock.patch(f"Commands.PythonCommandBase.{name}")
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)


class PickTest(unittest.TestCase):
    def test_unknown_values_mean_the_camera_image(self):
        self.assertEqual(notification_image.normalize("WINDOW "), notification_image.WINDOW)
        for value in ("", "screen", None, 1):
            self.assertEqual(notification_image.normalize(value), notification_image.CAMERA)
        self.assertEqual(set(notification_image.LABELS), set(notification_image.KINDS))

    def test_the_selected_image_is_used(self):
        window = mock.Mock(return_value="window image")
        self.assertEqual(notification_image.pick("camera", lambda: "camera image", window), "camera image")
        window.assert_not_called()
        self.assertEqual(notification_image.pick("window", lambda: "camera image", window), "window image")

    def test_the_camera_image_is_used_when_the_window_cannot_be_captured(self):
        # 最小化している間、Windows 以外など
        self.assertEqual(notification_image.pick("window", lambda: "camera image", lambda: None), "camera image")
        self.assertEqual(notification_image.pick("window", lambda: "camera image", None), "camera image")
        with self.assertLogs("services.notification_image", level="WARNING"):
            self.assertEqual(notification_image.pick("window", lambda: "camera image", mock.Mock(side_effect=OSError("x"))), "camera image")

    def test_no_image_when_the_camera_fails_too(self):
        with self.assertLogs("services.notification_image", level="WARNING"):
            self.assertIsNone(notification_image.pick("camera", mock.Mock(side_effect=RuntimeError("closed"))))

    def test_a_window_that_does_not_exist_is_not_captured(self):
        self.assertIsNone(WindowCapture.capture_whole_window(None))
        self.assertIsNone(WindowCapture.capture_whole_window(0))


class SettingTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.path = os.path.join(self.folder, "settings.ini")
        patcher = mock.patch.object(AppSettings, "SETTING_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def saved(self):
        parser = configparser.ConfigParser()
        parser.read(self.path, encoding="utf-8")
        return parser["Notification"].get(notification_image.SETTING_NAME)

    def test_default_is_the_camera_image_and_the_choice_is_saved(self):
        settings = AppSettings()
        settings.load()
        self.assertEqual(settings.discord_notification_image, notification_image.CAMERA)
        settings.discord_notification_image = notification_image.WINDOW
        settings.save()
        self.assertEqual(self.saved(), "window")
        again = AppSettings()
        again.load()
        self.assertEqual(again.discord_notification_image, notification_image.WINDOW)

    def test_a_settings_file_of_an_older_version_is_read(self):
        settings = AppSettings()
        settings.load()
        settings.save()
        parser = configparser.ConfigParser()
        parser.read(self.path, encoding="utf-8")
        parser.remove_option("Notification", notification_image.SETTING_NAME)
        with open(self.path, "w", encoding="utf-8") as file:
            parser.write(file)
        old = AppSettings()
        old.load()
        self.assertEqual(old.discord_notification_image, notification_image.CAMERA)


class StartAndEndNotificationTest(unittest.TestCase):
    def setUp(self):
        self.saved = Command._notification_image
        self.addCleanup(lambda: setattr(Command, "_notification_image", self.saved))
        self.command = PythonCommand()
        self.command.Discord = mock.Mock()
        self.command.Discord.resolve.return_value = "DISCORD_WEBHOOK"
        self.command.Discord.send_message.return_value = True

    def sent(self):
        return self.command.Discord.send_message.call_args.kwargs

    def test_the_selected_image_is_attached(self):
        Command._notification_image = lambda: "image"
        self.assertTrue(self.command._discordNotify("started."))
        self.assertEqual(self.sent(), {"notification_message": "started.", "image": "image", "keys": "DISCORD_WEBHOOK"})

    def test_only_the_text_is_sent_without_an_image(self):
        for provider in (None, lambda: None, mock.Mock(side_effect=RuntimeError("no camera"))):
            Command._notification_image = provider
            self.command.Discord.send_message.reset_mock()
            self.assertTrue(self.command._discordNotify("finished."))
            self.assertEqual(self.sent(), {"notification_message": "finished.", "keys": "DISCORD_WEBHOOK"})

    def test_a_failure_to_send_does_not_stop_the_command(self):
        Command._notification_image = lambda: "image"
        self.command.Discord.send_message.side_effect = OSError("no network")
        self.assertFalse(self.command._discordNotify("started."))
        self.command.Discord.resolve.return_value = None
        self.assertFalse(self.command._discordNotify("started."))

    def test_discord_image_of_scripts_does_not_use_the_setting(self):
        # スクリプトの discord_image が送るのは、いつも、カメラの画像(この設定の影響を受けない)
        import inspect

        from Commands.PythonCommandBase import ImageProcPythonCommand

        source = inspect.getsource(ImageProcPythonCommand.discord_image)
        self.assertNotIn("_notification_image", source)
        self.assertIn("readFrame", source)


if __name__ == "__main__":
    unittest.main()
