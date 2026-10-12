#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/device_service.py のテスト(画面を起動せず、カメラも開かずに実行できる)

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

from services import device_service  # noqa: E402


class DeviceServiceTest(unittest.TestCase):
    def test_windows_list_has_names_paths_and_disable(self):
        names = {0: "Capture A (path-a)", 1: "Capture B (path-b)"}
        paths = {0: "path-a", 1: "path-b"}
        with mock.patch.object(device_service.platform, "system", return_value="Windows"), mock.patch.object(
            device_service, "_list_cameras_windows", return_value=(dict(names), dict(paths))
        ):
            listed_names, listed_paths = device_service.list_cameras()
        self.assertEqual(listed_names, {0: "Capture A (path-a)", 1: "Capture B (path-b)", "2": "Disable"})
        self.assertEqual(listed_paths, paths)

    def test_windows_reports_the_reason_when_directshow_is_unavailable(self):
        # 以前は、別のライブラリ(windows-capture-device-list)を読み込もうとして、理由の分からない ModuleNotFoundError になった
        printed = io.StringIO()
        with mock.patch.dict(sys.modules, {"clr": None}), contextlib.redirect_stdout(printed):
            with self.assertRaises(RuntimeError) as raised:
                device_service._list_cameras_windows()
        self.assertIn("DirectShowLib でカメラの名前を取得できませんでした", str(raised.exception))
        self.assertNotIn("ブロックを解除", printed.getvalue())

    def test_windows_shows_how_to_unblock_the_dll(self):
        clr = mock.Mock()
        clr.AddReference.side_effect = OSError("HRESULT: 0x80131515")
        printed = io.StringIO()
        with mock.patch.dict(sys.modules, {"clr": clr}), contextlib.redirect_stdout(printed):
            with self.assertRaises(RuntimeError):
                device_service._list_cameras_windows()
        self.assertIn("DLLのブロックを解除してください", printed.getvalue())

    def test_mac_list_has_no_paths(self):
        with mock.patch.object(device_service.platform, "system", return_value="Darwin"), mock.patch.object(
            device_service, "_list_cameras_mac", return_value={0: "FaceTime HD Camera"}
        ):
            listed_names, listed_paths = device_service.list_cameras()
        self.assertEqual(listed_names, {0: "FaceTime HD Camera", "1": "Disable"})
        self.assertIsNone(listed_paths)

    def test_mac_output_is_split_into_names(self):
        result = mock.Mock(stdout="FaceTime HD Camera\nUSB Video\n\n".encode("utf-8"))
        with mock.patch.object(device_service.subprocess, "run", return_value=result):
            self.assertEqual(device_service._list_cameras_mac(), {0: "FaceTime HD Camera", 1: "USB Video"})

    def test_other_systems_cannot_list_names(self):
        with mock.patch.object(device_service.platform, "system", return_value="Linux"):
            self.assertIsNone(device_service.list_cameras())

    def test_labels(self):
        self.assertEqual(device_service.camera_labels({0: "A", "1": "Disable"}), ["No.0: A", "No.1: Disable"])

    def test_extra_sources_without_windows(self):
        sources = {"ext:a": ("Ext A", object())}
        with mock.patch.object(device_service, "EXTRA_SOURCES", sources), mock.patch.object(
            device_service, "list_windows", side_effect=AssertionError("ウィンドウは調べない")
        ):
            self.assertEqual(device_service.extra_source_labels(False, "viewer.exe|Class"), {"ext:a": "Ext A"})

    def test_extra_sources_keep_the_selected_window(self):
        window = mock.Mock(key="game.exe|Class", title="Game")
        with mock.patch.object(device_service, "EXTRA_SOURCES", {}), mock.patch.object(
            device_service, "list_windows", return_value=[window]
        ), mock.patch.object(device_service, "window_label", side_effect=lambda key, title="": f"Window: {title or key}"):
            labels = device_service.extra_source_labels(True, "closed.exe|Class")
        self.assertEqual(labels, {"game.exe|Class": "Window: Game", "closed.exe|Class": "Window: closed.exe|Class"})

    def test_replace_extra_sources_keeps_cameras(self):
        names = {0: "Capture A", "1": "Disable", 2: "Window: old 1", 3: "Window: old 2"}
        new_ids = device_service.replace_extra_sources(names, {2: "old1", 3: "old2"}, {"new": "Window: new"})
        self.assertEqual(names, {0: "Capture A", "1": "Disable", 2: "Window: new"})
        self.assertEqual(new_ids, {2: "new"})

    def test_audio_inputs_are_sorted_by_camera_number(self):
        numbers = {"Capture B": 1, "Capture A": 0}
        self.assertEqual(
            device_service.sort_audio_inputs(["Microphone", "Capture B", "Line", "Capture A"], numbers),
            ["Capture A", "Capture B", "Microphone", "Line"],
        )

    def test_list_audio_inputs(self):
        calls = []
        with mock.patch.object(device_service, "refresh_devices", side_effect=lambda: calls.append("refresh")), mock.patch.object(
            device_service, "list_input_devices", return_value=["Microphone", "Capture A"]
        ), mock.patch.object(device_service, "match_audio_to_cameras", return_value={"Capture A": 0}):
            self.assertEqual(device_service.list_audio_inputs({0: "path"}), (["Capture A", "Microphone"], {"Capture A": 0}))
            self.assertEqual(calls, ["refresh"])
            device_service.list_audio_inputs({0: "path"}, refresh=False)  # 取り込み中は接続・切断を反映しない
            self.assertEqual(calls, ["refresh"])

    def test_audio_label(self):
        self.assertEqual(device_service.audio_label("Capture A", {"Capture A": 0}), "No.0: Capture A")
        self.assertEqual(device_service.audio_label("Microphone", {"Capture A": 0}), "No.x: Microphone")

    def test_default_audio_input(self):
        names = ["Capture A", "Capture B", "Microphone"]
        numbers = {"Capture A": 0, "Capture B": 1}
        self.assertIsNone(device_service.default_audio_input(names, numbers, "Microphone", 1))  # 選択済み
        self.assertIsNone(device_service.default_audio_input([], numbers, "", 1))  # デバイスなし
        self.assertEqual(device_service.default_audio_input(names, numbers, "", 1), "Capture B")  # カメラと同じ機器
        self.assertEqual(device_service.default_audio_input(names, numbers, "Removed", 5), "Capture A")  # 先頭

    def test_module_does_not_import_tkinter(self):
        with io.open(device_service.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)


if __name__ == "__main__":
    unittest.main()
