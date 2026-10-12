#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/serial_service.py のテスト(画面を起動せず、ポートにもつながずに実行できる)

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

from Commands.Keys import InputSource, KeyPress  # noqa: E402
from Commands.Sender import Sender  # noqa: E402
from services import serial_service  # noqa: E402
from services.serial_service import SerialService, forced_baud_rate, port_number  # noqa: E402


class FakeSender:
    """ポートを開く代わりに、呼び出しを記録する Sender の代役"""

    def __init__(self, can_open=True):
        self.can_open = can_open
        self.opened = False
        self.calls = []

    def isOpened(self):
        return self.opened

    def openSerial(self, number, name="", baudrate=9600):
        self.calls.append(("open", number, name, baudrate))
        self.opened = self.can_open
        return self.can_open

    def closeSerial(self):
        self.calls.append(("close",))
        self.opened = False

    def __getattr__(self, name):
        # KeyPress が使うそのほかのメソッド
        return lambda *args, **kwargs: None


class FakePort:
    def __init__(self, description):
        self.description = description


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class SerialServiceTest(unittest.TestCase):
    def setUp(self):
        self.original_format = KeyPress.serial_data_format_name
        self.addCleanup(lambda: setattr(KeyPress, "serial_data_format_name", self.original_format))

    def test_port_number(self):
        self.assertEqual(port_number("USB-SERIAL CH340 (COM9)"), 9)
        self.assertEqual(port_number("USB Serial Port (COM12)"), 12)

    def test_ports_are_sorted_by_number(self):
        ports = [FakePort("B (COM12)"), FakePort("A (COM3)"), FakePort("C (COM9)")]
        with mock.patch.object(serial_service.list_ports, "comports", return_value=ports):
            self.assertEqual(SerialService(FakeSender()).list_port_descriptions(), ["A (COM3)", "C (COM9)", "B (COM12)"])

    def test_find_description(self):
        descriptions = ["A (COM3)", "C (COM9)"]
        self.assertEqual(SerialService.find_description(descriptions, 9), "C (COM9)")
        self.assertIsNone(SerialService.find_description(descriptions, 4))

    def test_forced_baud_rate(self):
        self.assertEqual(forced_baud_rate("Default"), 9600)
        self.assertEqual(forced_baud_rate("Qingpi"), 9600)
        self.assertEqual(forced_baud_rate("3DS Controller"), 115200)
        self.assertEqual(forced_baud_rate("3DS Controller(FW:x.4-)"), 115200)
        self.assertIsNone(forced_baud_rate("DS FT (Rev1)"))

    def test_set_data_format_switches_the_format_used_for_sending(self):
        service = SerialService(FakeSender())
        self.assertEqual(service.set_data_format("3DS Controller"), 115200)
        self.assertEqual(KeyPress.serial_data_format_name, "3DS Controller")

    def test_connect(self):
        sender = FakeSender()
        service = SerialService(sender)
        with quiet():
            self.assertTrue(service.connect(9, "", 9600))
        self.assertEqual(sender.calls, [("open", 9, "", 9600)])
        self.assertTrue(service.is_connected())
        self.assertIsInstance(service.key_press, KeyPress)
        self.assertEqual(service.key_press.source, InputSource.KEYBOARD)

    def test_connect_while_connected_reopens(self):
        sender = FakeSender()
        service = SerialService(sender)
        with quiet():
            service.connect(9, "", 9600)
            first = service.key_press
            service.connect(12, "", 115200)
        self.assertEqual(sender.calls, [("open", 9, "", 9600), ("close",), ("open", 12, "", 115200)])
        self.assertIsNot(service.key_press, first)

    def test_failed_connect_leaves_no_keyboard_input(self):
        sender = FakeSender()
        service = SerialService(sender)
        with quiet():
            service.connect(9, "", 9600)
            sender.can_open = False
            self.assertFalse(service.connect(99, "", 9600))
        self.assertIsNone(service.key_press)
        self.assertFalse(service.is_connected())

    def test_disconnect(self):
        sender = FakeSender()
        service = SerialService(sender)
        with quiet():
            service.connect(9, "", 9600)
            service.disconnect()
            service.disconnect()  # 切断済みなら何もしない
        self.assertEqual(sender.calls, [("open", 9, "", 9600), ("close",)])
        self.assertIsNone(service.key_press)

    def test_sender_accepts_plain_bool_for_show_serial(self):
        sender = Sender(False)
        self.assertIs(sender.show_serial, False)
        sender.set_show_serial(True)
        self.assertIs(sender.show_serial, True)

    def test_module_does_not_import_tkinter(self):
        with io.open(serial_service.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)


class OpenFailureTest(unittest.TestCase):
    """シリアルを開けなかったとき: 原因を表示し、ログにも残す(ログの出力でエラーにならない)"""

    def test_reason_is_printed_and_logged(self):
        import serial

        sender = Sender(mock.Mock())
        error = serial.SerialException("could not open port 'COM99'")
        out = io.StringIO()
        with mock.patch.object(serial, "Serial", side_effect=error), contextlib.redirect_stdout(
            out
        ), self.assertLogs(sender._logger, "ERROR") as logs:
            self.assertFalse(sender.openSerial(99, "COM99"))
        self.assertIn("COM Port: can't be established\ncould not open port 'COM99'\n", out.getvalue())
        # 機器の側の状態で開けないことがあるので、試すことを案内する
        self.assertIn("機器の抜き差しを行い、[Scan Device]+[Reload Port]を実施すると改善することがあります。\n", out.getvalue())
        self.assertEqual(len(logs.records), 1)
        # メッセージの組み立てでエラーにならず、原因が入っている
        self.assertEqual(logs.records[0].getMessage(), "COM Port: can't be established: could not open port 'COM99'")

if __name__ == "__main__":
    unittest.main()
