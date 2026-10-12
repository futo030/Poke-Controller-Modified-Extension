#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
層の決まりの検査: 画面に依存しない層が、画面(tkinter・ui・Window)を読み込んでいないこと

- services/ と Commands/transport/ の各ファイルと、コマンドの土台(Commands/ の基底クラスなど)が対象
- 型の注釈のためだけの import (if TYPE_CHECKING: の中)は、実行時に読み込まれないので除く

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import ast
import glob
import io
import os
import subprocess
import sys
import unittest

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 画面に依存しない層のファイル(SerialController フォルダから見た場所)
GUI_FREE_FILES = sorted(
    os.path.relpath(path, SERIAL_CONTROLLER_DIR).replace(os.sep, "/")
    for folder in (("services",), ("Commands", "transport"))
    for path in glob.glob(os.path.join(SERIAL_CONTROLLER_DIR, *folder, "*.py"))
) + [
    "Commands/CommandBase.py",
    "Commands/PythonCommandBase.py",
    "Commands/McuCommandBase.py",
    "Commands/UnitCommand.py",
    "Commands/Keys.py",
    "Commands/Sender.py",
    "Commands/InputRecorder.py",
    "Commands/ControllerProfile.py",
    "Commands/ControllerSetupSession.py",
    "CommandLoader.py",
    "Camera.py",
    "Audio.py",
    "AudioProcessing.py",
    "ImageProcessing.py",
    "Mask.py",
    "Profile.py",
    "OutputLinks.py",
    "UiDispatcher.py",
    "DeviceMatch.py",
    "WindowCapture.py",
    # レイアウトの内容の取り出し(describe_layout)は、tkinter なしで使える
    "ControllerLayouts.py",
    "ControllerColors.py",
    "Keyboard.py",
    "KeyMap.py",
]
# 画面の層のモジュール(画面に依存しない層からは読み込まない)
GUI_MODULES = ("tkinter", "ui", "Window", "Menubar", "GuiAssets", "Settings", "Theme", "PokeConDialogue")
# 例外: ダイアログの表示方法が登録されていない場合に限り、実行時に tkinter のダイアログを読み込む
# 例外: ControllerLayouts.py は、tkinter の画面に表示するとき(CanvasControllerGUI を作るとき)にだけ tkinter を読み込む
ALLOWED = {("Commands/CommandBase.py", "ui.dialogue"), ("ControllerLayouts.py", "tkinter")}


def runtime_imports(path: str) -> list:
    """
    実行時に読み込まれる import のモジュール名(if TYPE_CHECKING: の中は除く)
    """
    with io.open(os.path.join(SERIAL_CONTROLLER_DIR, path), encoding="utf-8") as file:
        tree = ast.parse(file.read())
    names = []

    def visit(node):
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            ):
                for child in node.orelse:
                    visit(child)
                return
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return names


class LayeringTest(unittest.TestCase):
    def test_files_exist(self):
        for path in GUI_FREE_FILES:
            self.assertTrue(os.path.isfile(os.path.join(SERIAL_CONTROLLER_DIR, path)), path)

    def test_gui_free_files_do_not_import_the_gui(self):
        violations = []
        for path in GUI_FREE_FILES:
            for name in runtime_imports(path):
                if name.split(".")[0] in GUI_MODULES and (path, name) not in ALLOWED:
                    violations.append(f"{path} imports {name}")
        self.assertEqual(violations, [])

    def test_web_version_does_not_import_the_tkinter_screen(self):
        # Web ブラウザ版の画面は、tkinter の画面(tkinter・ui・Window など)を使わない
        violations = []
        for path in sorted(glob.glob(os.path.join(SERIAL_CONTROLLER_DIR, "web", "*.py"))):
            relative = os.path.relpath(path, SERIAL_CONTROLLER_DIR).replace(os.sep, "/")
            for name in runtime_imports(relative):
                if name.split(".")[0] in GUI_MODULES:
                    violations.append(f"{relative} imports {name}")
        self.assertEqual(violations, [])

    def test_importing_the_services_does_not_load_tkinter(self):
        modules = [path[:-3].replace("/", ".") for path in GUI_FREE_FILES if not path.endswith("__init__.py")]
        code = (
            "import sys, importlib\n"
            f"for name in {modules!r}:\n"
            "    importlib.import_module(name)\n"
            "    if 'tkinter' in sys.modules:\n"
            "        sys.stderr.write('LOADED_BY=' + name)\n"
            "        break\n"
            "else:\n"
            "    sys.stderr.write('TKINTER=False')\n"
        )
        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", code], cwd=SERIAL_CONTROLLER_DIR, capture_output=True, timeout=180
        )
        stderr = result.stderr.decode("utf-8", "replace")
        self.assertEqual(result.returncode, 0, stderr[-800:])
        self.assertIn("TKINTER=False", stderr, stderr[-300:])


if __name__ == "__main__":
    unittest.main()
