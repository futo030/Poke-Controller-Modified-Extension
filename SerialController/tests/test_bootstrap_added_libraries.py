#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap/added_libraries.py(利用者が足したライブラリの検出)のテスト(何も入れない)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

REPOSITORY_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPOSITORY_DIR)

from bootstrap import added_libraries  # noqa: E402
from bootstrap.added_libraries import Candidate  # noqa: E402


class NameTest(unittest.TestCase):
    def test_names_are_compared_without_case_and_separators(self):
        self.assertEqual(added_libraries.normalize("Paho_MQTT"), "paho-mqtt")
        self.assertEqual(added_libraries.normalize("ruamel.yaml"), "ruamel-yaml")

    def test_requirement_name_drops_versions_and_markers(self):
        for text, name in (
            ("pynput>=1.7.7", "pynput"),
            ("uvicorn[standard]", "uvicorn"),
            ("colorama ; sys_platform == 'win32'", "colorama"),
            ("Pillow (>=10)", "pillow"),
        ):
            self.assertEqual(added_libraries.requirement_name(text), name)

    def test_project_names_come_from_pyproject(self):
        names = added_libraries.project_names(os.path.join(REPOSITORY_DIR, "pyproject.toml"))
        self.assertIn("opencv-python", names)
        self.assertIn("pillow", names)
        # 任意の追加分(Web ブラウザ版)も、本体の分として扱う
        self.assertIn("fastapi", names)


class CandidatesTest(unittest.TestCase):
    installed = {
        "numpy": set(),
        "pandas": {"numpy", "tzdata"},
        "tzdata": set(),
        "numba": {"numpy", "llvmlite"},
        "llvmlite": set(),
        "openpyxl": {"et-xmlfile"},
        "et-xmlfile": set(),
        "jupyter": set(),
        "pip": set(),
    }
    project = {"numpy", "pandas"}

    def candidates(self, imported, local=frozenset(), distributions_of=None):
        distributions_of = distributions_of or {"numba": ["numba"], "numpy": ["numpy"], "openpyxl": ["openpyxl"]}
        return added_libraries.candidates(self.installed, self.project, imported, set(local), distributions_of)

    def test_not_required_drops_dependencies_project_and_tools(self):
        self.assertEqual(added_libraries.not_required(self.installed, self.project), ["jupyter", "numba", "openpyxl"])

    def test_libraries_used_by_scripts_come_first(self):
        result = self.candidates({"numba": {"MyScript"}, "numpy": {"MyScript"}, "os": {"MyScript"}})
        self.assertEqual(result[0], Candidate("numba", ["MyScript"]))
        self.assertTrue(result[0].used_by_scripts)
        # スクリプトが使っていないものは、後ろに並ぶ(呼び出し側は、チェックを外して見せる)
        self.assertEqual([(c.name, c.used_by_scripts) for c in result[1:]], [("jupyter", False), ("openpyxl", False)])

    def test_local_modules_are_not_libraries(self):
        # 本体のフォルダーに同じ名前のファイルがあれば、import で読まれるのは、そちら
        result = self.candidates({"numba": {"MyScript"}}, local={"numba"})
        self.assertFalse(result[[c.name for c in result].index("numba")].used_by_scripts)

    def test_import_name_can_differ_from_the_library_name(self):
        installed = dict(self.installed, **{"pyserial": set()})
        result = added_libraries.candidates(installed, self.project, {"serial": {"A", "B"}}, set(), {"serial": ["pyserial"]})
        self.assertEqual(result[0], Candidate("pyserial", ["A", "B"]))

    def test_imports_that_are_not_installed_are_ignored(self):
        self.assertNotIn("pyaudio", [c.name for c in self.candidates({"pyaudio": {"Sample"}})])


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def write(self, name, text):
        path = os.path.join(self.folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write(text)

    def test_imports_are_read_without_running_the_scripts(self):
        self.write("Mine/main.py", "import numba.core\nfrom openpyxl import Workbook\nfrom . import helper\nraise SystemExit\n")
        self.write("single.py", "import numba, os\n")
        self.write("Broken/bad.py", "def (:\n")
        self.assertEqual(
            added_libraries.imported_names(self.folder),
            {"numba": {"Mine", "single.py"}, "openpyxl": {"Mine"}, "os": {"single.py"}},
        )

    def test_local_names_are_files_and_folders(self):
        self.write("services/tools.py", "")
        self.write("Window.py", "")
        self.assertEqual(added_libraries.local_names(self.folder), {"services", "tools", "Window"})

    def test_user_requirements_keep_existing_lines(self):
        path = added_libraries.write_user_requirements(self.folder, ["Numba", "openpyxl"])
        added_libraries.write_user_requirements(self.folder, ["numba", "pyocr"])
        with open(path, encoding="utf-8") as file:
            lines = file.read().splitlines()
        self.assertTrue(lines[0].startswith("#"))
        self.assertEqual(lines[1:], ["numba", "openpyxl", "pyocr"])

    def test_detect_runs_on_this_repository(self):
        # 今の環境とスクリプトを読むだけで、例外にならないこと
        for candidate in added_libraries.detect(REPOSITORY_DIR):
            self.assertNotIn(candidate.name, added_libraries.TOOLS)


if __name__ == "__main__":
    unittest.main()
