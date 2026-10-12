#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Status タブに表示する文字(services/status_text.py)のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import status_text as st  # noqa: E402


class StatusTextTest(unittest.TestCase):
    def test_camera_name_is_cut_before_the_device_path(self):
        self.assertEqual(st.camera_name("No.0: USB Video (@device:pnp:usb#vid_534d)"), "No.0: USB Video")
        self.assertEqual(st.camera_name("No.1: Game Capture (HD60) (@device:sw:{860B})"), "No.1: Game Capture (HD60)")
        self.assertEqual(st.camera_name("No.0: USB Video"), "No.0: USB Video")

    def test_camera(self):
        self.assertEqual(st.camera_text("No.0: USB Video (@device:pnp)", "1280x720", True),
                         "No.0: USB Video (Capture Size: 1280x720)")
        self.assertEqual(st.camera_text("No.0: USB Video", "1280x720", False), st.NOT_OPENED)
        self.assertEqual(st.camera_text("", "640x480", True), "(名前なし) (Capture Size: 640x480)")

    def test_audio(self):
        self.assertEqual(st.audio_input_text("No.0: USB Audio", True), "No.0: USB Audio")
        self.assertEqual(st.audio_input_text("No.0: USB Audio", False), st.NOT_USED)
        self.assertEqual(st.audio_input_text("", False, available=False), st.NOT_AVAILABLE)
        self.assertEqual(st.audio_output_text("Default", True, True), "Default")
        self.assertEqual(st.audio_output_text("Default", True, False), st.NO_PLAYBACK)
        self.assertEqual(st.audio_output_text("Default", False, True), st.NOT_USED)
        self.assertEqual(st.audio_output_text("", False, False, available=False), st.NOT_AVAILABLE)

    def test_serial(self):
        # 名前にポートが入っているときは、重ねて出さない
        self.assertEqual(st.serial_text("USB Serial Port (COM3)", 3, "9600", True), "USB Serial Port (COM3) (Baud Rate: 9600)")
        self.assertEqual(st.serial_text("USB-SERIAL CH340 (COM13)", 13, 9600, True), "USB-SERIAL CH340 (COM13) (Baud Rate: 9600)")
        # 名前に入っていないとき(別の番号が入っているときを含む)は、ポートも出す
        self.assertEqual(st.serial_text("USB-SERIAL CH340 (COM13)", 1, 9600, True), "USB-SERIAL CH340 (COM13) (COM1, Baud Rate: 9600)")
        self.assertEqual(st.serial_text("USB Serial Port", 3, 9600, True), "USB Serial Port (COM3, Baud Rate: 9600)")
        self.assertEqual(st.serial_text("", 5, 115200, True), "COM5, Baud Rate: 115200")
        self.assertEqual(st.serial_text("ttyUSB", 0, 9600, True, port_label="Port "), "ttyUSB (Port 0, Baud Rate: 9600)")
        self.assertEqual(st.serial_text("USB Serial Port (COM3)", 3, "9600", False), st.NOT_CONNECTED)

    def test_command(self):
        started = datetime(2026, 10, 11, 9, 5, 7)
        # 開始時間は、名前とは別の行(名前が長いと、後ろに付けた時刻が見えなくなるため)
        self.assertEqual(st.command_text("自動孵化"), "自動孵化")
        self.assertEqual(st.command_text(None), st.NO_COMMAND)
        self.assertEqual(st.started_text("自動孵化", started), "2026/10/11 09:05:07")
        self.assertEqual(st.started_text("自動孵化", None), st.UNKNOWN_TIME)
        self.assertEqual(st.started_text(None, started), st.NO_COMMAND)


if __name__ == "__main__":
    unittest.main()
