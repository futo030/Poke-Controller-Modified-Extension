#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Switch へのキーボード入力(TypeString / TypeKey など)が、送るデータの形式ごとに、機器へ送るデータのテスト。

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import transport_scenarios  # noqa: E402
from Commands import PythonCommandBase  # noqa: E402
from Commands.Keys import Button, InputSource, KeyPress  # noqa: E402
from Commands.PythonCommandBase import PythonCommand  # noqa: E402
from Commands.Sender import Sender  # noqa: E402
from Commands.SwitchKeyboard import KEY  # noqa: E402


def setUpModule():
    """通知のクラスを代役にする(コマンドを作るたびに、本物の通知先へ接続を確かめに行かないようにする)"""
    for name in ("Line_Notify", "Discord_Notify"):
        patcher = mock.patch(f"Commands.PythonCommandBase.{name}")
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)

class KeyboardInputTest(unittest.TestCase):
    def setUp(self):
        self.original_format = KeyPress.serial_data_format_name
        self.addCleanup(lambda: setattr(KeyPress, "serial_data_format_name", self.original_format))
        # 待ち時間は実際には待たず、長さだけ記録する
        self.waits = []
        for name in ("precise_sleep",):
            patcher = mock.patch.object(PythonCommandBase, name, lambda seconds: self.waits.append(round(seconds, 3)))
            patcher.start()
            self.addCleanup(patcher.stop)
        # (長い待機を、途中で止める指示を確かめるために区切らない。区切ると、実際に待ってしまう)
        patcher = mock.patch.object(PythonCommandBase, "STOP_POLL_INTERVAL", float("inf"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def command(self, format_name: str):
        KeyPress.serial_data_format_name = format_name
        self.log = []
        self.printed = io.StringIO()
        sender = Sender(False)
        sender.ser = transport_scenarios.FakeSerial(self.log)
        command = PythonCommand()
        command.keys = KeyPress(sender, InputSource.COMMAND)
        command.alive = True
        return command

    def run_steps(self, command):
        with contextlib.redirect_stdout(self.printed):
            command.KeyBoard_Init()
            results = [command.TypeString("neko"), command.TypeStringln("a long text 0123")]
            command.TypeKey(KEY.ENTER)
            command.TypeKey(KEY.SPACE)
            command.PressKey(KEY.BACKSPACE)
            command.ReleaseKey(KEY.BACKSPACE)
            command.PressKey(KEY.LEFT_ARROW)
            # 押したままのキーは、終了時に離す
            command._releaseKeyboardKeys()
            results.append(command.TypeString("全角"))
        return results

    def test_default_sends_text_rows(self):
        command = self.command("Default")
        self.assertEqual(self.run_steps(command), [True, True, False])
        self.assertEqual(
            self.log,
            [
                "text end",
                'text "neko"',
                'text "a long text 0"',
                'text "123"',
                "text Key 40",
                "text Key 40",
                "text Key 32",
                "text Press 42",
                "text Release 42",
                "text Press 80",
                "text Release 80",
            ],
        )
        self.assertEqual(self.waits, [0.05, 0.34, 0.88, 0.28, 0.16, 0.16, 0.16, 0.13, 0.13, 0.13, 0.13])

    def test_nx_sends_keyboard_actions_with_the_controller_state(self):
        command = self.command("NX")
        with contextlib.redirect_stdout(self.printed):
            command.KeyBoard_Init()
            self.assertTrue(command.TypeString("aB"))
            command.TypeKey(KEY.ENTER)
            command.TypeKey(KEY.SPACE)
            # ボタンを押したままでも、キーボードの操作と一緒に送る(ボタンは押したまま)
            command.keys.input(Button.A)
            command.PressKey(KEY.LEFT_ARROW)
            command.ReleaseKey(KEY.LEFT_ARROW)
            command.PressKey(KEY.BACKSPACE)
            command._releaseKeyboardKeys()
            self.assertFalse(command.TypeString("全角"))
        neutral = "ab 00 00 08 80 80 80 80"
        pressed = "ab 04 00 08 80 80 80 80"
        self.assertEqual(
            self.log,
            [
                f"bytes {neutral} 05 00 00",  # すべてのキーを離す
                f"bytes {neutral} 01 61 00",  # a を押す(文字コード)
                f"bytes {neutral} 02 61 00",
                f"bytes {neutral} 01 42 00",  # B
                f"bytes {neutral} 02 42 00",
                f"bytes {neutral} 03 28 00",  # Enter(キーコード)
                f"bytes {neutral} 04 28 00",
                f"bytes {neutral} 01 20 00",  # スペース(文字コード)
                f"bytes {neutral} 02 20 00",
                f"bytes {pressed} 00 00 00",  # A ボタン
                f"bytes {pressed} 03 50 00",  # ← を押したまま
                f"bytes {pressed} 04 50 00",
                f"bytes {pressed} 03 2a 00",  # BackSpace を押したまま
                f"bytes {pressed} 04 2a 00",  # 終了時に離す
            ],
        )
        self.assertEqual(self.waits, [0.05] + [0.03] * 8 + [0.03] * 4)
        self.assertEqual(self.printed.getvalue().count("NX"), 0)

    def test_formats_without_keyboard_send_nothing(self):
        for name in ("Qingpi", "3DS Controller(FW:x.4-)"):
            with self.subTest(format=name):
                command = self.command(name)
                self.assertEqual(self.run_steps(command), [False, False, False])
                self.assertEqual(self.log, [])
                # 使えないことは、1回だけ知らせる
                self.assertEqual(self.printed.getvalue().count(name), 1)
                self.assertIn("Default / NX", self.printed.getvalue())

    def test_keyboard_keeps_the_controller_state_in_default(self):
        command = self.command("Default")
        with contextlib.redirect_stdout(self.printed):
            command.keys.input(Button.A)
            command.TypeKey(KEY.ENTER)
        self.assertEqual(self.log, ["text 0x0013 8 80 80 80 80", "text Key 40"])


if __name__ == "__main__":
    unittest.main()
