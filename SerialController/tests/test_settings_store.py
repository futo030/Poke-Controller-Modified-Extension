#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/settings_store.py のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import configparser
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Profile  # noqa: E402
from services import settings_store  # noqa: E402
from services.settings_store import AppSettings  # noqa: E402


class AppSettingsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.path = os.path.join(self.directory, "settings.ini")
        self.original_path = AppSettings.SETTING_PATH
        AppSettings.SETTING_PATH = self.path
        self.addCleanup(self.cleanup)

    def cleanup(self):
        AppSettings.SETTING_PATH = self.original_path
        Profile.set_read_only(False)
        shutil.rmtree(self.directory, ignore_errors=True)

    def read_file(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(self.path, encoding="utf-8")
        return parser

    def test_missing_file_is_generated_with_defaults(self):
        settings = AppSettings()
        self.assertTrue(os.path.isfile(self.path))
        self.assertEqual(settings.camera_id, 0)
        self.assertEqual(settings.baud_rate, 9600)
        self.assertEqual(settings.fps, "45")
        self.assertEqual(settings.capture_size, "1280x720")
        self.assertIs(settings.is_use_keyboard, True)
        self.assertIs(settings.is_show_value, False)
        self.assertEqual(settings.serial_data_format_name, "Default")
        self.assertEqual(settings.command_class_dict["1"], "None")
        self.assertEqual(settings.command_name_dict["12"], "(empty)")
        self.assertEqual(settings.command_history, [])
        self.assertEqual(settings.side_panel_position, "right")

    def test_values_are_plain_python_values(self):
        settings = AppSettings()
        for name, kind in settings_store.VARIABLE_FIELDS:
            self.assertIsInstance(getattr(settings, name), kind, name)

    def test_changed_values_are_saved_and_read_back(self):
        settings = AppSettings()
        settings.camera_id = 3
        settings.capture_window = "viewer 100%.exe|Class"
        settings.is_use_audio = True
        settings.audio_volume = 55
        settings.is_discord_notification_end = True
        settings.command_class_dict["2"] = "Python"
        settings.command_name_dict["2"] = "A連打"
        settings.command_history.append({"class": "Python", "name": "A連打", "last_run": "2026-10-05 12:00:00"})
        settings.masks = ["Rectangle,1,2,3,4,#000000,True"]
        settings.side_panel_position = "bottom"
        settings.touchscreen_start_x = 12
        self.assertEqual(settings.log_level, "debug")
        settings.log_level = "warning"
        settings.save()

        loaded = AppSettings()
        self.assertEqual(loaded.camera_id, 3)
        self.assertEqual(loaded.capture_window, "viewer 100%.exe|Class")
        self.assertIs(loaded.is_use_audio, True)
        self.assertEqual(loaded.audio_volume, 55)
        self.assertIs(loaded.is_discord_notification_end, True)
        self.assertEqual(loaded.command_class_dict["2"], "Python")
        self.assertEqual(loaded.command_name_dict["2"], "A連打")
        self.assertEqual(loaded.command_history, [{"class": "Python", "name": "A連打", "last_run": "2026-10-05 12:00:00"}])
        self.assertEqual(loaded.masks, ["Rectangle,1,2,3,4,#000000,True"])
        self.assertEqual(loaded.side_panel_position, "bottom")
        self.assertEqual(loaded.touchscreen_start_x, 12)
        self.assertEqual(loaded.log_level, "warning")

    def test_missing_optional_items_use_defaults(self):
        AppSettings()
        parser = self.read_file()
        for key in ("capture_size", "audio_volume", "is_audio_playback", "serial_data_format_name", "touchscreen_end_x"):
            parser.remove_option("General Setting", key)
        parser.remove_section("Notification")
        parser.remove_option("Output", "widget_mode")
        with open(self.path, "w", encoding="utf-8") as file:
            parser.write(file)

        settings = AppSettings()
        self.assertEqual(settings.capture_size, "1280x720")
        self.assertEqual(settings.audio_volume, 100)
        self.assertIs(settings.is_audio_playback, True)
        self.assertEqual(settings.serial_data_format_name, "Default")
        self.assertEqual(settings.touchscreen_end_x, 320)
        self.assertIs(settings.is_win_notification_start, False)
        self.assertEqual(settings.right_frame_widget_mode, "ALL (default)")

    def test_key_config_saved_by_another_window_is_kept(self):
        settings = AppSettings()
        parser = self.read_file()
        parser.set("KeyMap-Button", "Button.A", "z")
        with open(self.path, "w", encoding="utf-8") as file:
            parser.write(file)
        settings.save()
        self.assertEqual(self.read_file().get("KeyMap-Button", "Button.A"), "z")

    def test_read_only_profile_is_not_saved(self):
        settings = AppSettings()
        with io.open(self.path, encoding="utf-8") as file:
            before = file.read()
        Profile.set_read_only(True)
        settings.camera_id = 9
        settings.save()
        with io.open(self.path, encoding="utf-8") as file:
            self.assertEqual(file.read(), before)

    def test_read_theme(self):
        settings = AppSettings()
        self.assertEqual(AppSettings.readTheme(), "default")
        settings.theme = "dark_a"
        settings.save()
        self.assertEqual(AppSettings.readTheme(), "dark_a")

    def test_read_theme_of_another_file(self):
        # 起動時は、設定ファイルの場所を切り替える前に、プロファイルの設定ファイルからテーマを読む
        settings = AppSettings()
        settings.theme = "dark_a"
        settings.save()
        other = os.path.join(self.directory, "other.ini")
        with io.open(other, "w", encoding="utf-8") as file:
            file.write("[Output]\ntheme = light_d\n")
        self.assertEqual(AppSettings.readTheme(other), "light_d")
        self.assertEqual(AppSettings.readTheme(), "dark_a")
        # まだ作られていないプロファイル(ファイルがない)は、デフォルト
        self.assertEqual(AppSettings.readTheme(os.path.join(self.directory, "none", "settings.ini")), "default")

    def test_module_does_not_import_tkinter(self):
        with io.open(settings_store.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)


if __name__ == "__main__":
    unittest.main()
