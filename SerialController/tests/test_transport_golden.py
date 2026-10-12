#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
送信方式(Commands/transport)のテスト。

- 形式ごとに決まった入力を行い、機器へ送るデータが、記録(tests/data/transport_golden.json)と
  1バイトも違わないことを確かめる。記録は、形式ごとの処理を1か所にまとめる前のコードで作ったもの
- 登録簿と、形式を足す場合の動きを確かめる

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import transport_scenarios  # noqa: E402
from Commands import FtdiPort as ftdi  # noqa: E402
from Commands.Keys import Button, InputSource, KeyPress, Touchscreen  # noqa: E402
from Commands.Sender import Sender  # noqa: E402
from Commands.transport import Transport, ds_ft, get_transport, port_transport, registry, transport_names  # noqa: E402
from services import serial_service, settings_control  # noqa: E402


class GoldenTest(unittest.TestCase):
    """送るデータが、これまでと変わらないこと"""

    @classmethod
    def setUpClass(cls):
        with io.open(transport_scenarios.GOLDEN_FILE, encoding="utf-8") as file:
            cls.golden = json.load(file)

    def test_every_recorded_format_is_checked(self):
        self.assertEqual(sorted(self.golden), sorted(transport_scenarios.FORMATS))
        # 登録簿にある形式は、すべて記録がある(足したのに記録を作り忘れることを防ぐ)
        self.assertEqual(sorted(transport_names(available_only=False)), sorted(self.golden))

    def test_sent_data_is_unchanged(self):
        for name in transport_scenarios.FORMATS:
            with self.subTest(format=name):
                actual = transport_scenarios.run_format(name)
                expected = self.golden[name]
                self.assertEqual(actual["sent"], expected["sent"])
                self.assertEqual({k: v for k, v in actual.items() if k != "sent"},
                                 {k: v for k, v in expected.items() if k != "sent"})


class RegistryTest(unittest.TestCase):
    def test_names_and_order(self):
        names = transport_names(available_only=False)
        self.assertEqual(
            names,
            [
                "Default", "NX", "Qingpi", "3DS Controller(FW:x.4-)", "3DS Controller(FW:-x.3)",
                "DS FT (Rev3)", "DS FT (Rev2)", "DS FT (Rev1)",
            ],
        )
        self.assertEqual(sorted(names[5:]), sorted(ftdi.FTDI_FORMATS))
        for name in names:
            self.assertEqual(get_transport(name).name, name)

    def test_unknown_names(self):
        # 登録のない名前は、これまでの判定と同じ形式になる
        self.assertEqual(get_transport("no such format").name, "Default")
        self.assertEqual(get_transport("").name, "Default")
        self.assertEqual(get_transport("3DS Controller(new)").name, "3DS Controller(FW:x.4-)")
        self.assertEqual(get_transport("old 3DS Controller x.3").name, "3DS Controller(FW:-x.3)")

    def test_ds_ft_needs_the_startup_option_and_the_library(self):
        always = ["Default", "NX", "Qingpi", "3DS Controller(FW:x.4-)", "3DS Controller(FW:-x.3)"]
        transport = get_transport("DS FT (Rev1)")
        self.addCleanup(ds_ft.set_enabled, ds_ft.is_enabled())
        # 起動時に --ds_ft を付けていない: ftd2xx があっても、一覧に出さない
        ds_ft.set_enabled(False)
        for library in (True, False):
            with mock.patch.object(ftdi, "FTDI_AVAILABLE", library):
                self.assertEqual(settings_control.serial_formats(), always)
                self.assertFalse(transport.is_available())
                self.assertIn("--ds_ft", transport.unavailable_message())
        # --ds_ft を付けた: ftd2xx がある場合だけ、一覧に出す
        ds_ft.set_enabled(True)
        with mock.patch.object(ftdi, "FTDI_AVAILABLE", False):
            self.assertEqual(settings_control.serial_formats(), always)
            self.assertFalse(transport.is_available())
            self.assertIn("ftd2xx", transport.unavailable_message())
        with mock.patch.object(ftdi, "FTDI_AVAILABLE", True):
            self.assertEqual(settings_control.serial_formats(), transport_names(available_only=False))
            self.assertTrue(transport.is_available())

    def test_the_option_is_off_by_default(self):
        import subprocess

        code = "from Commands.transport import ds_ft, transport_names; print(ds_ft.is_enabled(), transport_names())"
        folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out = subprocess.run([sys.executable, "-c", code], cwd=folder, capture_output=True, text=True).stdout
        self.assertIn("False ['Default', 'NX', 'Qingpi', '3DS Controller(FW:x.4-)', '3DS Controller(FW:-x.3)']", out)

    def test_the_open_port_decides_the_transport(self):
        # FTDI のデバイスを開いたまま形式を切り替えても、接続し直すまでは、FTDI として扱う
        port = ftdi.FtdiPort(transport_scenarios.FakeFtdiDevice([]), "DS FT (Rev2)")
        self.assertEqual(port_transport(port, "Default").name, "DS FT (Rev2)")
        self.assertEqual(port_transport(transport_scenarios.FakeSerial([]), "Qingpi").name, "Qingpi")
        self.assertEqual(port_transport(None, "Default").name, "Default")

    def test_duplicate_or_nameless_transports_are_refused(self):
        with self.assertRaises(ValueError):
            registry.register(get_transport("Default"))
        with self.assertRaises(ValueError):
            registry.register(Transport())


class NewTransportTest(unittest.TestCase):
    """形式を足す場合: クラスを1つ作って登録するだけで、送信・一覧・ボーレートに反映される"""

    class Sample(Transport):
        name = "Sample (test)"
        baud_rate = 57600
        has_touchscreen = True

        def encode(self, state, last_sent, encoder, port):
            return bytes([0xEE, state["btn"] & 0xFF, state["hat"], state["sx"] & 0xFF, state["sy"] & 0xFF])

    def setUp(self):
        self.original_format = KeyPress.serial_data_format_name
        registry.register(self.Sample())
        self.addCleanup(lambda: registry._transports.pop("Sample (test)", None))
        self.addCleanup(lambda: setattr(KeyPress, "serial_data_format_name", self.original_format))

    def test_a_registered_transport_is_used_everywhere(self):
        name = "Sample (test)"
        self.assertEqual(settings_control.serial_formats()[-1], name)
        self.assertEqual(serial_service.forced_baud_rate(name), 57600)
        KeyPress.serial_data_format_name = name
        log = []
        with contextlib.redirect_stdout(io.StringIO()):
            sender = Sender(False)
            sender.ser = transport_scenarios.FakeSerial(log)
            keys = KeyPress(sender, InputSource.COMMAND)
            keys.input([Button.A, Touchscreen(7, 9)])
            keys.end()
            # 合成を経由しない送信は、止めない形式
            sender.writeRow("end")
        self.assertEqual(log, ["bytes ee 04 08 07 09", "bytes ee 00 08 00 00", "text end"])


if __name__ == "__main__":
    unittest.main()
