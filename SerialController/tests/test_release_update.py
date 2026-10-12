#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/release_update.py(Git を使わない更新: Release の ZIP での入れ替え)のテスト(通信はしない)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import release_update  # noqa: E402
from services.release_update import UpdateError  # noqa: E402

OLD = {
    "README.md": "old readme\n",
    "SerialController/Window.py": "window 1\n",
    "SerialController/Utility.py": "utility\n",
    "SerialController/removed.py": "removed\n",
    "SerialController/removed_but_edited.py": "original\n",
    "SerialController/db/data.csv": "a,b\n",
    "SerialController/profiles/default/settings.ini": "[General Setting]\ncom_port = 1\n",
    "SerialController/Commands/PythonCommands/Samples/sample.py": "sample 1\n",
}
NEW = {
    "README.md": "new readme\n",
    "SerialController/Window.py": "window 2\n",
    "SerialController/Utility.py": "utility\n",
    "SerialController/added.py": "added\n",
    "SerialController/profiles/default/settings.ini": "[General Setting]\ncom_port = 2\n",
    "SerialController/Commands/PythonCommands/Samples/sample.py": "sample 2\n",
}

URLS = {"old": "https://example.invalid/v1.zip", "new": "https://example.invalid/v2.zip"}


def make_zip(files: dict, top: str = "Repo-v1") -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, text in files.items():
            archive.writestr(f"{top}/{name}", text)
    return data.getvalue()


class Folder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.local = os.path.join(self.folder, "local")

    def write(self, root, files, newline="\n"):
        for name, text in files.items():
            path = os.path.join(root, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline=newline) as file:
                file.write(text)

    def read(self, name):
        with open(os.path.join(self.local, *name.split("/")), encoding="utf-8") as file:
            return file.read()

    def exists(self, name):
        return os.path.exists(os.path.join(self.local, *name.split("/")))

    def opener(self, zips):
        def open_url(request, timeout=None):
            if request.full_url not in zips:
                raise OSError("HTTP Error 404: Not Found")
            return contextlib.closing(io.BytesIO(zips[request.full_url]))

        return open_url

    def update(self, zips=None):
        zips = {"old": make_zip(OLD), "new": make_zip(NEW, "Repo-v2")} if zips is None else zips
        zips = {URLS[name]: data for name, data in zips.items()}
        return release_update.update(
            self.local, URLS["old"], URLS["new"], log=lambda text: None, opener=self.opener(zips), now=datetime(2026, 10, 12, 1, 2, 3)
        )


class UpdateTest(Folder):
    def test_only_files_changed_between_the_versions_are_touched(self):
        self.write(self.local, OLD)
        self.write(self.local, {"SerialController/Commands/PythonCommands/mine.py": "my script\n", "notes.txt": "mine\n"})
        result = self.update()
        self.assertEqual(self.read("README.md"), "new readme\n")
        self.assertEqual(self.read("SerialController/Window.py"), "window 2\n")
        self.assertEqual(self.read("SerialController/added.py"), "added\n")
        self.assertEqual(self.read("SerialController/Commands/PythonCommands/Samples/sample.py"), "sample 2\n")
        # 新しい版でなくなったファイルは消える(空になったフォルダーも)
        self.assertFalse(self.exists("SerialController/removed.py"))
        self.assertFalse(self.exists("SerialController/db"))
        # どちらの版にもないファイル(利用者のもの)は、そのまま
        self.assertEqual(self.read("SerialController/Commands/PythonCommands/mine.py"), "my script\n")
        self.assertEqual(self.read("notes.txt"), "mine\n")
        self.assertEqual(result.failed, [])
        self.assertIsNone(result.backup_dir)
        self.assertNotIn("SerialController/Utility.py", result.plan.replace)

    def test_files_edited_by_the_user_are_backed_up_first(self):
        self.write(self.local, OLD)
        self.write(self.local, {"SerialController/Window.py": "my window\n", "SerialController/removed_but_edited.py": "edited\n"})
        result = self.update()
        self.assertEqual(result.backup_dir, os.path.join(self.local, "old", "20261012010203"))
        self.assertEqual(sorted(result.plan.backup), ["SerialController/Window.py", "SerialController/removed_but_edited.py"])
        self.assertEqual(self.read("old/20261012010203/SerialController/Window.py"), "my window\n")
        self.assertEqual(self.read("old/20261012010203/SerialController/removed_but_edited.py"), "edited\n")
        self.assertEqual(self.read("SerialController/Window.py"), "window 2\n")
        self.assertFalse(self.exists("SerialController/removed_but_edited.py"))

    def test_files_not_changed_between_the_versions_keep_the_user_edits(self):
        self.write(self.local, OLD)
        self.write(self.local, {"SerialController/Utility.py": "my utility\n"})
        result = self.update()
        self.assertEqual(self.read("SerialController/Utility.py"), "my utility\n")
        self.assertEqual(result.plan.backup, [])

    def test_user_settings_are_never_replaced(self):
        # プロファイルの設定は、リポジトリに登録されているが、利用者が書き換えて使うもの
        self.write(self.local, OLD)
        self.write(self.local, {"SerialController/profiles/default/settings.ini": "[General Setting]\ncom_port = 13\n"})
        self.update()
        self.assertIn("com_port = 13", self.read("SerialController/profiles/default/settings.ini"))

    def test_a_file_placed_by_the_user_under_a_new_name_is_backed_up(self):
        self.write(self.local, OLD)
        self.write(self.local, {"SerialController/added.py": "mine\n"})
        result = self.update()
        self.assertEqual(result.plan.backup, ["SerialController/added.py"])
        self.assertEqual(self.read("old/20261012010203/SerialController/added.py"), "mine\n")
        self.assertEqual(self.read("SerialController/added.py"), "added\n")

    def test_line_endings_are_not_a_change(self):
        # git の設定によって、手元は CRLF、ZIP は LF になる
        self.write(self.local, OLD, newline="\r\n")
        result = self.update()
        self.assertEqual(result.plan.backup, [])
        self.assertEqual(self.read("README.md"), "new readme\n")

    def test_a_missing_or_already_updated_file_is_handled(self):
        self.write(self.local, OLD)
        os.remove(os.path.join(self.local, "README.md"))
        self.write(self.local, {"SerialController/Window.py": "window 2\n"})
        result = self.update()
        self.assertEqual(self.read("README.md"), "new readme\n")
        self.assertNotIn("SerialController/Window.py", result.plan.replace)
        self.assertEqual(result.plan.backup, [])

    def test_nothing_changes_when_a_download_fails(self):
        self.write(self.local, OLD)
        with self.assertRaises(UpdateError):
            self.update({"new": make_zip(NEW)})  # 手元の版の ZIP がない(タグのない版など)
        with self.assertRaises(UpdateError):
            self.update({"old": make_zip(OLD), "new": b"not a zip"})
        self.assertEqual(self.read("README.md"), "old readme\n")
        self.assertTrue(self.exists("SerialController/removed.py"))
        self.assertFalse(self.exists("old"))

    def test_names_pointing_outside_are_refused(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("Repo-v2/../../evil.py", "x")
        self.write(self.local, OLD)
        with self.assertRaises(UpdateError):
            self.update({"old": make_zip(OLD), "new": data.getvalue()})
        self.assertFalse(os.path.exists(os.path.join(self.folder, "evil.py")))

    def test_a_file_that_cannot_be_replaced_is_reported_and_the_rest_continue(self):
        self.write(self.local, OLD)
        # 入れ替え先がフォルダーになっている(書き込めない場合の代わり)
        os.remove(os.path.join(self.local, "README.md"))
        os.makedirs(os.path.join(self.local, "README.md", "x"))
        result = self.update()
        self.assertEqual([name for name, _ in result.failed], ["README.md"])
        self.assertEqual(self.read("SerialController/Window.py"), "window 2\n")


if __name__ == "__main__":
    unittest.main()
