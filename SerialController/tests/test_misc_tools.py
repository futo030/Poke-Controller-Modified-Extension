#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
こまごました機能のテスト(画面を起動せずに実行できる)
- PokeConLogger.py: ログのファイルの名前(log_プロファイル名_日時.log)
- services/note_store.py: Note の読み書き
- services/diagnostics.py: 環境の診断
- Commands/Sender.py: すべての入力を離す

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import logging
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import PokeConLogger  # noqa: E402
import transport_scenarios  # noqa: E402
from Commands.Keys import Button, InputSource, KeyPress  # noqa: E402
from Commands.Sender import Sender  # noqa: E402
from Commands.transport import get_transport  # noqa: E402
from services import diagnostics, note_store  # noqa: E402
from services.settings_store import AppSettings  # noqa: E402

BS = chr(92)


class TempFolderCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))


class LogFileTest(TempFolderCase):
    def setUp(self):
        super().setUp()
        root = logging.getLogger()
        before, level = list(root.handlers), root.level
        saved = (PokeConLogger._early_handler, PokeConLogger._log_file_path)
        current = os.getcwd()
        os.chdir(self.folder)

        def restore():
            os.chdir(current)
            for handler in [handler for handler in root.handlers if handler not in before]:
                root.removeHandler(handler)
                handler.close()
            root.setLevel(level)
            PokeConLogger._early_handler, PokeConLogger._log_file_path = saved

        self.addCleanup(restore)
        PokeConLogger._early_handler = PokeConLogger._log_file_path = None
        patcher = mock.patch.object(PokeConLogger, "time", "20261011-120000")
        patcher.start()
        self.addCleanup(patcher.stop)

    def files(self):
        return sorted(os.listdir(os.path.join(self.folder, "log")))

    def read(self, name):
        for handler in logging.getLogger().handlers:
            handler.flush()
        with open(os.path.join(self.folder, "log", name), encoding="utf-8") as file:
            return file.read()

    def test_file_name_has_the_profile_name(self):
        self.assertEqual(PokeConLogger.log_file_name("default"), "log_default_20261011-120000.log")
        self.assertEqual(PokeConLogger.log_file_name("サブ機 2"), "log_サブ機 2_20261011-120000.log")
        # ファイルの名前に使えない文字は、置き換える
        self.assertEqual(PokeConLogger.log_file_name('a/b\\c:d*e?f"g<h>i|j'), "log_a_b_c_d_e_f_g_h_i_j_20261011-120000.log")
        self.assertEqual(PokeConLogger.log_file_name(""), "log___20261011-120000.log")

    def test_file_is_created_with_the_profile_given_at_start(self):
        with contextlib.redirect_stderr(io.StringIO()):
            PokeConLogger.root_logger("test2")
            logging.getLogger("x").info("hello")
        self.assertEqual(self.files(), ["log_test2_20261011-120000.log"])
        self.assertIn("[INFO]: hello", self.read("log_test2_20261011-120000.log"))
        self.assertEqual(PokeConLogger.log_file_path(), os.path.abspath(os.path.join("log", "log_test2_20261011-120000.log")))

    def test_records_before_the_profile_is_chosen_are_written_later(self):
        with contextlib.redirect_stderr(io.StringIO()):
            PokeConLogger.root_logger()
            self.assertEqual(self.files(), [])
            self.assertIsNone(PokeConLogger.log_file_path())
            logging.getLogger("x").info("before the profile")
            path = PokeConLogger.set_profile("default")
            logging.getLogger("x").warning("after the profile")
        self.assertEqual(self.files(), ["log_default_20261011-120000.log"])
        self.assertEqual(path, PokeConLogger.log_file_path())
        text = self.read("log_default_20261011-120000.log")
        self.assertLess(text.index("before the profile"), text.index("after the profile"))
        self.assertEqual(text.count("before the profile"), 1)
        # 覚えておくためのハンドラーは、外してある
        self.assertFalse(any(isinstance(h, PokeConLogger.EarlyRecords) for h in logging.getLogger().handlers))

    def test_set_profile_twice_keeps_the_first_file(self):
        with contextlib.redirect_stderr(io.StringIO()):
            PokeConLogger.root_logger()
            first = PokeConLogger.set_profile("a")
            second = PokeConLogger.set_profile("b")
        self.assertEqual(first, second)
        self.assertEqual(self.files(), ["log_a_20261011-120000.log"])
        self.assertEqual(sum(isinstance(h, logging.FileHandler) for h in logging.getLogger().handlers), 1)

    def test_early_records_are_limited(self):
        handler = PokeConLogger.EarlyRecords(capacity=3)
        logger = logging.Logger("early", logging.DEBUG)
        logger.addHandler(handler)
        for i in range(10):
            logger.info("line %d", i)
        self.assertEqual([record.getMessage() for record in handler.records], ["line 7", "line 8", "line 9"])


class NoteStoreTest(TempFolderCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(AppSettings, "SETTING_PATH", os.path.join(self.folder, "profile", "settings.ini"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = os.path.join(self.folder, "profile", "note.txt")

    def test_the_file_is_next_to_the_settings_of_the_profile(self):
        self.assertEqual(note_store.note_path(), self.path)

    def test_missing_file_is_empty(self):
        self.assertEqual(note_store.load(), "")

    def test_save_and_load(self):
        text = "色違い 3 匹目\n  メモ: 5 番道路\n\n日本語と emoji 🎮\n"
        self.assertTrue(note_store.save(text))
        self.assertEqual(note_store.load(), text)
        with open(self.path, "rb") as file:
            self.assertEqual(file.read(), text.encode("utf-8"))
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["note.txt"])

    def test_empty_note_can_be_saved(self):
        note_store.save("x")
        self.assertTrue(note_store.save(""))
        self.assertEqual(note_store.load(), "")

    def test_line_endings_and_bom_are_normalized_when_read(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "wb") as file:
            file.write(b"\xef\xbb\xbfa\r\nb\rc\n")
        self.assertEqual(note_store.load(), "a\nb\nc\n")

    def test_unreadable_and_unwritable_files_do_not_raise(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "wb") as file:
            file.write(b"\xff\xfe\x00broken")
        with self.assertLogs(note_store._logger, "WARNING"):
            self.assertEqual(note_store.load(), "")
        blocked = os.path.join(self.folder, "file")
        with open(blocked, "w"):
            pass
        with self.assertLogs(note_store._logger, "WARNING"):
            self.assertFalse(note_store.save("x", os.path.join(blocked, "note.txt")))


class DiagnosticsTest(TempFolderCase):
    def levels(self, items):
        return {item.title: item.level for item in items}

    def test_requirement_names(self):
        path = os.path.join(self.folder, "requirements.txt")
        with open(path, "w", encoding="utf-8") as file:
            file.write("# comment\nopencv-python\npynput>=1.7.7\n\nPillow  # image\nrequests==2.0 ; python_version > '3'\n")
        self.assertEqual(diagnostics.requirement_names(path), ["opencv-python", "pynput", "Pillow", "requests"])
        self.assertIsNone(diagnostics.requirement_names(os.path.join(self.folder, "none.txt")))

    def test_libraries(self):
        path = os.path.join(self.folder, "requirements.txt")
        with open(path, "w", encoding="utf-8") as file:
            file.write("numpy\npyserial\n")
        items = diagnostics.check_libraries(path)
        self.assertEqual(items[0].level, diagnostics.OK)
        self.assertIn("numpy", items[1].detail)
        with open(path, "w", encoding="utf-8") as file:
            file.write("numpy\nno-such-core-library\nno-such-library\n")
        with mock.patch.object(diagnostics, "CORE_LIBRARIES", ("numpy", "no-such-core-library")):
            items = diagnostics.check_libraries(path)
        self.assertEqual([(item.level, item.detail.split(": ")[-1]) for item in items[:2]],
                         [(diagnostics.ERROR, "no-such-core-library"), (diagnostics.WARNING, "no-such-library")])
        self.assertEqual(diagnostics.check_libraries(os.path.join(self.folder, "none.txt"))[0].level, diagnostics.WARNING)

    def test_environment_tells_uv_from_the_old_one(self):
        venv = os.path.join(self.folder, ".venv")
        old = diagnostics.check_environment(os.path.join(self.folder, "Python312"), self.folder)[0]
        self.assertEqual(old.level, diagnostics.INFO)
        self.assertIn("ver.0.3.0 以降は、uv の環境が必要", old.detail)
        os.makedirs(venv)
        self.assertEqual(diagnostics.check_environment(os.path.join(self.folder, "Python312"), self.folder)[0].level, diagnostics.WARNING)
        self.assertEqual(diagnostics.check_environment(venv, self.folder)[0].level, diagnostics.OK)
        self.assertTrue(diagnostics.in_uv_environment(venv, self.folder))

    def test_optional_libraries_are_never_errors(self):
        with mock.patch.object(diagnostics, "OPTIONAL_LIBRARIES", (("no-such-library", "何かの機能"),)):
            items = diagnostics.check_libraries(os.path.join(os.path.dirname(diagnostics.SERIAL_CONTROLLER_DIR), "requirements.txt"))
        self.assertEqual((items[-1].level, "何かの機能" in items[-1].detail), (diagnostics.INFO, True))

    def test_folders(self):
        for name in ("profiles/p1", "log", "Commands/PythonCommands"):
            os.makedirs(os.path.join(self.folder, name))
        with open(os.path.join(self.folder, "log", "log_p1_x.log"), "w") as file:
            file.write("x" * 100)
        levels = self.levels(diagnostics.check_folders("p1", self.folder))
        self.assertEqual(levels["フォルダー: 設定(プロファイル)"], diagnostics.OK)
        self.assertEqual(levels["フォルダー: ログ"], diagnostics.OK)
        # ないフォルダーは、書き込めない扱い
        self.assertEqual(levels["フォルダー: テンプレート画像"], diagnostics.WARNING)
        self.assertEqual(levels["ディスクの空き"], diagnostics.OK)
        self.assertEqual(levels["ログのファイル"], diagnostics.INFO)
        self.assertEqual(self.levels(diagnostics.check_folders("none", self.folder))["フォルダー: 設定(プロファイル)"], diagnostics.ERROR)
        # 確かめるために作ったファイルは、残さない
        self.assertEqual(os.listdir(os.path.join(self.folder, "profiles", "p1")), [])

    def test_low_disk_space_and_many_logs_are_warnings(self):
        os.makedirs(os.path.join(self.folder, "log"))
        with mock.patch.object(diagnostics, "DISK_FREE_WARNING", 10 ** 30), mock.patch.object(diagnostics, "LOG_FILES_WARNING", 0):
            with open(os.path.join(self.folder, "log", "a.log"), "w"):
                pass
            levels = self.levels(diagnostics.check_folders("p", self.folder))
        self.assertEqual((levels["ディスクの空き"], levels["ログのファイル"]), (diagnostics.WARNING, diagnostics.WARNING))

    def test_devices(self):
        context = {"serial_connected": True, "serial_port": "COM13", "data_format": "Default", "camera_opened": True,
                   "camera_name": "Camera ID 0", "capture_size": "1280x720"}
        levels = self.levels(diagnostics.check_devices(context, ports=[("COM13", "USB-SERIAL CH340")]))
        self.assertEqual(levels, {"シリアル": diagnostics.OK, "PC にあるポート": diagnostics.INFO, "カメラ": diagnostics.OK})
        context.update(serial_connected=False, camera_opened=False)
        items = diagnostics.check_devices(context, ports=[])
        self.assertEqual(self.levels(items), {"シリアル": diagnostics.WARNING, "PC にあるポート": diagnostics.WARNING,
                                             "カメラ": diagnostics.WARNING})
        self.assertIn("COM13", items[0].detail)
        # 画面が状態を渡さなかった項目は、調べない
        self.assertEqual(list(self.levels(diagnostics.check_devices({}, ports=[("COM1", "x")]))), ["PC にあるポート"])

    def test_app(self):
        items = diagnostics.check_app({"app": "App ver.1", "profile": "p", "read_only": True,
                                       "command_counts": {"Python": 0, "Mcu": 0}, "log_file": "C:/log/log_p_x.log"})
        self.assertEqual([item.level for item in items],
                         [diagnostics.INFO, diagnostics.WARNING, diagnostics.WARNING, diagnostics.INFO])
        items = diagnostics.check_app({"app": "App", "profile": "p", "command_counts": {"Python": 3, "Mcu": 0}})
        self.assertEqual([item.level for item in items], [diagnostics.INFO, diagnostics.OK])

    def test_whole_diagnosis_runs_on_this_pc(self):
        items = diagnostics.diagnose({"app": "App", "profile": "default"})
        titles = [item.title for item in items]
        for title in ("アプリ", "OS", "Python", "ディスクの空き"):
            self.assertIn(title, titles)
        self.assertTrue(all(item.level in (diagnostics.OK, diagnostics.WARNING, diagnostics.ERROR, diagnostics.INFO) for item in items))
        text = diagnostics.to_text(items)
        self.assertEqual(text.splitlines()[0], diagnostics.summary(items))
        self.assertIn("[情報] アプリ: App / プロファイル: default", text)

    def test_onedrive_is_found_by_the_environment_variables(self):
        root = os.path.join(self.folder, "Cloud")
        inside = os.path.join(root, "Documents", "PokeCon", "SerialController")
        for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            with self.subTest(name=name):
                self.assertEqual(diagnostics.onedrive_folder(inside, {name: root}), os.path.abspath(root))
        # 大文字と小文字の違い・末尾の区切りは、気にしない(Windows)
        if os.name == "nt":
            self.assertIsNotNone(diagnostics.onedrive_folder(inside.upper(), {"OneDrive": root + os.sep}))
        # 名前が似ているだけの、別のフォルダーは、中とみなさない
        self.assertIsNone(diagnostics.onedrive_folder(os.path.join(self.folder, "CloudBackup", "PokeCon"), {"OneDrive": root}))
        self.assertIsNone(diagnostics.onedrive_folder(inside, {"OneDrive": ""}))

    def test_onedrive_is_found_by_the_folder_name(self):
        for folder in ("OneDrive", "onedrive", "OneDrive - 会社の名前"):
            with self.subTest(folder=folder):
                path = os.path.join(self.folder, folder, "ドキュメント", "PokeCon")
                found = diagnostics.onedrive_folder(path, {})
                self.assertEqual(os.path.normcase(found), os.path.normcase(os.path.join(self.folder, folder)))
        for folder in ("OneDriveTools", "MyOneDrive", "Documents"):
            with self.subTest(folder=folder):
                self.assertIsNone(diagnostics.onedrive_folder(os.path.join(self.folder, folder, "PokeCon"), {}))

    def test_location_inside_onedrive_is_a_warning(self):
        inside = os.path.join(self.folder, "OneDrive", "PokeCon", "SerialController")
        item = diagnostics.check_location(inside, {})[0]
        self.assertEqual((item.level, item.title), (diagnostics.WARNING, "置いている場所"))
        for word in ("OneDrive の中で動かしています", "同期", "コマンドが正常に動かない", "OneDrive の外"):
            self.assertIn(word, item.detail)
        outside = diagnostics.check_location(os.path.join(self.folder, "PokeCon", "SerialController"), {})[0]
        self.assertEqual((outside.level, outside.title), (diagnostics.OK, "置いている場所"))

    def test_location_is_part_of_the_whole_diagnosis(self):
        with mock.patch.object(diagnostics, "onedrive_folder", lambda path, environ=None: "C:/Users/x/OneDrive"):
            items = diagnostics.diagnose({"app": "App", "profile": "default"})
        location = next(item for item in items if item.title == "置いている場所")
        self.assertEqual(location.level, diagnostics.WARNING)
        self.assertIn("注意が", diagnostics.summary(items))
        self.assertIn("[注意] 置いている場所: OneDrive の中で動かしています", diagnostics.to_text(items))

    def test_versions_that_the_old_version_window_showed_are_listed(self):
        items = diagnostics.diagnose({"app": "App ver.9", "profile": "default"})
        text = diagnostics.to_text(items)
        for word in ("App ver.9", "] OS: ", "] Python: ", "ライブラリの版: ", "pyserial ", "sounddevice", "fastapi"):
            self.assertIn(word, text)

    def test_folders_above_the_app_folder_are_masked(self):
        base = r"C:#Users#Taro Yamada#Documents#GitHub#PokeCon#SerialController".replace("#", BS)
        home = r"C:#Users#Taro Yamada".replace("#", BS)
        text = (
            "[OK] 置いている場所: " + base + "@"
            "[OK] フォルダー: ログ: " + base + BS + "log@"
            "[情報] 今のログ: " + base.replace(BS, "/") + "/log/log_default_x.log@"
            "[OK] Python: 3.12(64 bit) " + home + BS + "AppData" + BS + "Local" + BS + "Python312" + BS + "python.exe@"
            "[OK] 別の場所: C:" + BS + "Program Files" + BS + "Python312" + BS + "python.exe@"
            "[情報] 大文字と小文字: " + base.upper() + BS + "Template@"
        ).replace("@", chr(10))
        masked = diagnostics.mask_paths(text, base, home)
        lines = masked.splitlines()
        self.assertEqual(lines[0], "[OK] 置いている場所: ***" + BS + "SerialController")
        self.assertEqual(lines[1], "[OK] フォルダー: ログ: ***" + BS + "SerialController" + BS + "log")
        self.assertEqual(lines[2], "[情報] 今のログ: ***/SerialController/log/log_default_x.log")
        # アプリのフォルダーの外にある、ユーザーのフォルダーも隠す
        self.assertEqual(lines[3], "[OK] Python: 3.12(64 bit) ***" + BS + "AppData" + BS + "Local" + BS + "Python312" + BS + "python.exe")
        # 関係のない場所は、そのまま
        self.assertEqual(lines[4], "[OK] 別の場所: C:" + BS + "Program Files" + BS + "Python312" + BS + "python.exe")
        self.assertEqual(lines[5], "[情報] 大文字と小文字: ***" + BS + "SERIALCONTROLLER" + BS + "Template")
        for word in ("Taro", "Yamada", "GitHub", "PokeCon", "Documents"):
            self.assertNotIn(word.lower(), masked.lower())

    def test_a_folder_with_a_similar_name_is_not_masked(self):
        base = r"C:#work#PokeCon#SerialController".replace("#", BS)
        other = r"C:#work#PokeCon2#file.txt".replace("#", BS)
        self.assertEqual(diagnostics.mask_paths(other, base, ""), other)
        self.assertEqual(diagnostics.mask_paths(r"C:#work#PokeCon".replace("#", BS), base, ""), "***")

    def test_masked_text_of_this_pc_hides_the_folders(self):
        items = diagnostics.diagnose({"app": "App", "profile": "default",
                                      "log_file": os.path.join(diagnostics.SERIAL_CONTROLLER_DIR, "log", "log_default_x.log")})
        plain, masked = diagnostics.to_text(items), diagnostics.to_text(items, mask=True)
        parent = os.path.dirname(diagnostics.SERIAL_CONTROLLER_DIR)
        self.assertIn(parent, plain)
        self.assertNotIn(parent.lower(), masked.lower())
        self.assertIn("***" + os.sep + "SerialController" + os.sep + "log" + os.sep + "log_default_x.log", masked)
        # 場所のほかは、同じ(行の数も、見出しも変わらない)
        self.assertEqual(len(plain.splitlines()), len(masked.splitlines()))
        self.assertEqual([line.split(": ")[0] for line in plain.splitlines()], [line.split(": ")[0] for line in masked.splitlines()])

    def test_summary(self):
        make = diagnostics.Item
        self.assertEqual(diagnostics.summary([make(diagnostics.OK, "a"), make(diagnostics.INFO, "b")]), "問題は見つかりませんでした。")
        self.assertIn("注意が 2 件", diagnostics.summary([make(diagnostics.WARNING, "a"), make(diagnostics.WARNING, "b")]))
        self.assertIn("NG が 1 件、注意が 1 件", diagnostics.summary([make(diagnostics.ERROR, "a"), make(diagnostics.WARNING, "b")]))


class CoreReleaseAllTest(unittest.TestCase):
    """AppCore(Web ブラウザ版の本体)の「すべての入力を離す」"""

    def core(self, opened, keyboard=True):
        from types import SimpleNamespace

        calls = []
        return calls, SimpleNamespace(
            softcon=SimpleNamespace(release_all=lambda: calls.append("softcon")),
            simulator=SimpleNamespace(release_all=lambda: calls.append("simulator")),
            keyboard=SimpleNamespace(releaseAll=lambda: calls.append("keyboard")) if keyboard else None,
            sender=SimpleNamespace(isOpened=lambda: opened, release_all=lambda end_row: calls.append(("sender", end_row))),
            settings=SimpleNamespace(serial_data_format_name="Default"),
            _notify=lambda topic: calls.append(("notify", topic)),
        )

    def test_everything_is_released(self):
        from services.app_core import AppCore

        calls, core = self.core(opened=True)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            AppCore.release_all_inputs(core)
        self.assertEqual(calls, ["softcon", "simulator", "keyboard", ("sender", "end"), ("notify", "input")])
        self.assertEqual(printed.getvalue().strip(), "すべての入力を離しました。")

    def test_without_a_connection_nothing_is_sent(self):
        from services.app_core import AppCore

        calls, core = self.core(opened=False, keyboard=False)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            AppCore.release_all_inputs(core)
        self.assertEqual(calls, ["softcon", "simulator", ("notify", "input")])
        self.assertIn("シリアルに接続していないので", printed.getvalue())


class ReleaseAllTest(unittest.TestCase):
    def setUp(self):
        self.original = KeyPress.serial_data_format_name
        self.addCleanup(lambda: setattr(KeyPress, "serial_data_format_name", self.original))

    def sender(self, format_name):
        KeyPress.serial_data_format_name = format_name
        self.log = []
        sender = Sender(False)
        sender.ser = transport_scenarios.FakeSerial(self.log)
        return sender

    def test_all_sources_are_released_with_the_end_row(self):
        sender = self.sender("Default")
        command = KeyPress(sender, InputSource.COMMAND)
        mouse = KeyPress(sender, InputSource.MOUSE)
        with contextlib.redirect_stdout(io.StringIO()):
            command.input(Button.A)
            mouse.input(Button.B)
            self.assertEqual(len(sender._layers), 2)
            del self.log[:]
            sender.release_all(get_transport("Default").end_row)
        self.assertEqual(len(sender._layers), 0)
        self.assertEqual(self.log, ["text end"])

    def test_neutral_state_is_sent_when_the_format_has_no_end_row(self):
        sender = self.sender("NX")
        self.assertIsNone(get_transport("NX").end_row)
        keys = KeyPress(sender, InputSource.COMMAND)
        with contextlib.redirect_stdout(io.StringIO()):
            keys.input(Button.A)
            pressed = self.log[-1]
            sender.release_all(None)
        released = self.log[-1]
        self.assertEqual(len(sender._layers), 0)
        self.assertNotEqual(released, pressed)
        # 何も押していない状態(押してから離したときに送るデータと、同じ)
        other = self.sender("NX")
        idle = KeyPress(other, InputSource.COMMAND)
        with contextlib.redirect_stdout(io.StringIO()):
            idle.input(Button.A)
            idle.inputEnd(Button.A)
        self.assertEqual(released, self.log[-1])

    def test_release_all_with_nothing_pressed(self):
        sender = self.sender("Default")
        with contextlib.redirect_stdout(io.StringIO()):
            sender.release_all(get_transport("Default").end_row)
        self.assertEqual(self.log, ["text end"])

    def test_sources_can_send_again_after_release_all(self):
        sender = self.sender("Default")
        keys = KeyPress(sender, InputSource.COMMAND)
        with contextlib.redirect_stdout(io.StringIO()):
            keys.input(Button.A)
            sender.release_all("end")
            del self.log[:]
            keys.input(Button.B)
        self.assertEqual(len(sender._layers), 1)
        self.assertEqual(len(self.log), 1)


if __name__ == "__main__":
    unittest.main()
