#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/settings_control.py と services/audio_service.py のテスト(カメラも音声デバイスも開かずに実行できる)

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
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Audio import AudioError  # noqa: E402
from Commands.CommandBase import Command  # noqa: E402
from services import audio_service, device_service, settings_control  # noqa: E402
from services.audio_service import AudioService  # noqa: E402
from services.output_service import OutputService  # noqa: E402
from services.settings_control import SettingError, SettingsControl  # noqa: E402

COMMAND_FLAGS = (
    "isSimilarity", "isGuide", "stdout_destination", "pos_dialogue_buttons",
    "isWinNotStart", "isWinNotEnd", "isLineNotStart", "isLineNotEnd", "isDiscordNotStart", "isDiscordNotEnd",
)


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def make_settings(**overrides):
    values = dict(
        camera_id=0, capture_window="", capture_size="1280x720", fps="45", is_use_mjpg=False, is_show_windows=False,
        preview_gain=100, preview_gamma=1.0, com_port=3, baud_rate=9600, serial_data_format_name="Default",
        is_show_serial=False, is_use_audio=False, audio_device="", is_audio_playback=True, audio_output_device="",
        audio_volume=100, software_controller_layout="Switch (Joy-Con)", is_show_realtime=True, controller_device="Auto", controller_layout="Switch (Joy-Con)",
        is_show_value=False, is_show_guide=False, stdout_destination="1", pos_dialogue_buttons="2",
        is_win_notification_start=False, is_win_notification_end=False, is_line_notification_start=False,
        is_line_notification_end=False, is_discord_notification_start=False, is_discord_notification_end=False,
    )
    values.update(overrides)
    settings = SimpleNamespace(**values)
    settings.saved = 0
    settings.save = lambda: setattr(settings, "saved", settings.saved + 1)
    return settings


class FakeCapture:
    """音声デバイスを開かない AudioCapture の代役"""

    def __init__(self):
        self.is_running = False
        self.is_playing = False
        self.device_name = ""
        self.samplerate, self.channels = 48000, 2
        self.output_device_name = ""
        self.volume = None
        self.calls = []
        self.start_error = None
        self.playback_error = None

    def start(self, name):
        if self.start_error is not None:
            raise self.start_error
        self.calls.append(("start", name))
        self.device_name = name
        self.is_running = True

    def stop(self):
        self.calls.append(("stop",))
        self.is_running = self.is_playing = False

    def set_volume(self, volume):
        self.volume = volume

    def set_playback(self, enabled):
        if self.playback_error is not None and enabled:
            raise self.playback_error
        self.is_playing = enabled

    def set_output_device(self, name):
        self.calls.append(("output", name))
        self.output_device_name = name


class AudioServiceTest(unittest.TestCase):
    def setUp(self):
        self.settings = make_settings()
        self.capture = FakeCapture()
        self.service = AudioService(self.settings, self.capture)
        for name, value in (
            ("list_audio_inputs", lambda paths, refresh=True: (["Capture B", "Capture A", "Microphone"], {"Capture A": 0, "Capture B": 1})),
            ("list_audio_outputs", lambda refresh=True: ["Speaker"]),
        ):
            patcher = mock.patch.object(device_service, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_off_only_lists_devices(self):
        self.service.apply({}, 0)
        self.assertFalse(self.service.is_running)
        self.assertEqual(self.service.outputs, ["Speaker"])
        self.assertEqual(self.service.label("Capture A"), "No.0: Capture A")
        self.assertEqual(self.service.label("Microphone"), "No.x: Microphone")

    def test_on_starts_the_device_of_the_selected_camera(self):
        self.settings.is_use_audio = True
        self.settings.audio_volume = 50
        with quiet():
            self.service.apply({}, 1)
        self.assertEqual(self.settings.audio_device, "Capture B")
        self.assertTrue(self.service.is_running)
        self.assertTrue(self.capture.is_playing)
        self.assertEqual(self.capture.volume, 0.5)

    def test_selected_device_is_kept(self):
        self.settings.is_use_audio = True
        self.settings.audio_device = "Microphone"
        with quiet():
            self.service.apply({}, 1)
        self.assertEqual(self.capture.device_name, "Microphone")

    def test_start_error_turns_audio_off(self):
        self.settings.is_use_audio = True
        self.capture.start_error = AudioError("cannot open")
        with quiet():
            self.service.apply({}, 0)
        self.assertFalse(self.settings.is_use_audio)
        self.assertFalse(self.service.is_running)

    def test_playback_error_keeps_capturing(self):
        self.settings.is_use_audio = True
        self.capture.playback_error = AudioError("no output")
        with quiet():
            self.service.apply({}, 0)
        self.assertTrue(self.service.is_running)
        self.assertFalse(self.settings.is_audio_playback)

    def test_output_name(self):
        self.assertEqual(self.service.output_name(), "")
        self.settings.audio_output_device = audio_service.OUTPUT_DEFAULT
        self.assertEqual(self.service.output_name(), "")
        self.settings.audio_output_device = "Speaker"
        self.assertEqual(self.service.output_name(), "Speaker")

    def test_without_audio_support(self):
        service = AudioService(self.settings, None)
        with mock.patch.object(audio_service, "AUDIO_AVAILABLE", False):
            service = AudioService(self.settings)
        self.assertFalse(service.available)
        service.apply({}, 0)
        service.stop()
        self.assertFalse(service.is_running)


class FakeCore:
    def __init__(self):
        self.settings = make_settings()
        self.capture_window = ""
        self.camera = SimpleNamespace(capture_size=(1280, 720), fps=45)
        self.output = OutputService()
        self.audio = AudioService(self.settings, FakeCapture())
        self.serial = SimpleNamespace(list_port_descriptions=lambda: ["USB-SERIAL CH340 (COM13)", "Port (COM3)"])
        self.sender = SimpleNamespace(show=None, set_show_serial=lambda value: setattr(self.sender, "show", value))
        self.calls = []
        self.topics = []

    def open_camera(self):
        # アプリ本体と同じく、設定から取り込む対象を決める
        self.capture_window = self.settings.capture_window
        self.calls.append(("open_camera", self.settings.camera_id, self.capture_window))

    def connect_serial(self):
        self.calls.append(("connect_serial", self.settings.serial_data_format_name))

    def set_softcon_layout(self, name, color_settings=None):
        self.settings.software_controller_layout = name
        self.calls.append(("set_softcon_layout", name))

    def set_simulator_layout(self, name):
        self.settings.controller_layout = name
        self.calls.append(("set_simulator_layout", name))

    def _notify(self, topic):
        self.topics.append(topic)


class SettingsControlTest(unittest.TestCase):
    def setUp(self):
        self.saved_flags = {name: getattr(Command, name) for name in COMMAND_FLAGS}
        self.original_stdout = sys.stdout
        self.addCleanup(self.cleanup)
        self.core = FakeCore()
        self.control = SettingsControl(self.core)
        patches = (
            (device_service, "list_cameras", lambda: ({0: "Capture A (path-a)", 1: "Capture B (path-b)", "2": "Disable"}, {0: "path-a", 1: "path-b"})),
            (device_service, "extra_source_labels", lambda show, selected="": {"game.exe|Class": "Window: Game [game.exe]"} if show else {}),
            (device_service, "list_audio_inputs", lambda paths, refresh=True: (["Capture A", "Microphone"], {"Capture A": 0})),
            (device_service, "list_audio_outputs", lambda refresh=True: ["Speaker"]),
            (settings_control.platform, "system", lambda: "Windows"),
        )
        for target, name, value in patches:
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with quiet():
            self.control.scan(announce=False)

    def cleanup(self):
        for name, value in self.saved_flags.items():
            setattr(Command, name, value)
        sys.stdout = self.original_stdout

    def test_options_and_values_can_be_sent_as_json(self):
        options = self.control.options()
        json.dumps(options)
        json.dumps(self.control.values())
        self.assertEqual(
            options["cameras"],
            [{"id": 0, "label": "No.0: Capture A (path-a)"}, {"id": 1, "label": "No.1: Capture B (path-b)"}, {"id": 2, "label": "No.2: Disable"}],
        )
        self.assertEqual(options["ports"], [{"number": 13, "label": "USB-SERIAL CH340 (COM13)"}, {"number": 3, "label": "Port (COM3)"}])
        self.assertEqual(options["audio_inputs"], [{"name": "Capture A", "label": "No.0: Capture A"}, {"name": "Microphone", "label": "No.x: Microphone"}])
        self.assertEqual(options["audio_outputs"], ["Default", "Speaker"])
        self.assertIn("Default", options["formats"])
        self.assertEqual(self.control.values()["camera_source"], 0)
        self.assertEqual(self.control.values()["audio_output_device"], "Default")

    def test_every_change_is_saved_and_announced(self):
        self.control.apply("is_show_guide", True)
        self.assertEqual((self.core.settings.saved, self.core.topics), (1, ["settings"]))
        self.assertIs(Command.isGuide, True)

    def test_unknown_or_bad_values_are_refused(self):
        for name, value in (("no_such_setting", 1), ("capture_size", "12x34"), ("fps", "999"), ("baud_rate", 1234),
                            ("serial_data_format_name", "Other"), ("stdout_destination", "3"), ("camera_source", 9),
                            ("audio_device", "Unknown"), ("com_port", -1), ("save", 1), ("core", 1)):
            with self.assertRaises(SettingError, msg=name):
                self.control.apply(name, value)
        self.assertEqual(self.core.settings.saved, 0)
        self.assertEqual(self.core.calls, [])

    def test_camera_source(self):
        self.control.apply("camera_source", 1)
        self.assertEqual(self.core.calls, [("open_camera", 1, "")])
        self.assertEqual(self.control.values()["camera_source"], 1)

    def test_window_source(self):
        self.control.apply("is_show_windows", True)
        cameras = self.control.options()["cameras"]
        self.assertEqual(cameras[-1], {"id": 3, "label": "No.3: Window: Game [game.exe]"})
        self.control.apply("camera_source", 3)
        self.assertEqual(self.core.calls[-1], ("open_camera", 3, "game.exe|Class"))
        self.assertEqual(self.control.values()["camera_source"], 3)
        # ウィンドウを取り込んでいる間にチェックを外すと、カメラ(No.0)に戻して開き直す
        self.control.apply("is_show_windows", False)
        self.assertEqual(self.core.calls[-1], ("open_camera", 0, ""))
        self.assertEqual(len(self.control.options()["cameras"]), 3)

    def test_capture_size_reopens_the_camera_only_when_changed(self):
        with quiet():
            self.control.apply("capture_size", "1280x720")
            self.assertEqual(self.core.calls, [])
            self.control.apply("capture_size", "1920x1080")
        self.assertEqual(self.core.camera.capture_size, (1920, 1080))
        self.assertEqual(len(self.core.calls), 1)

    def test_fps_reopens_the_camera_only_with_mjpg(self):
        with quiet():
            self.control.apply("fps", "30")
            self.assertEqual((self.core.camera.fps, self.core.calls), (30, []))
            self.control.apply("is_use_mjpg", True)
            self.control.apply("fps", "60")
        self.assertEqual(len(self.core.calls), 2)

    def test_preview_brightness_is_kept_in_range(self):
        self.control.apply("preview_gain", 1000)
        self.control.apply("preview_gamma", "0.1")
        self.assertEqual((self.core.settings.preview_gain, self.core.settings.preview_gamma), (300, 0.5))
        self.assertEqual(self.core.calls, [])

    def test_serial(self):
        self.control.apply("com_port", "13")
        self.control.apply("baud_rate", "115200")
        self.assertEqual((self.core.settings.com_port, self.core.settings.baud_rate, self.core.calls), (13, 115200, []))
        self.control.apply("serial_data_format_name", "Qingpi")
        self.assertEqual(self.core.calls, [("connect_serial", "Qingpi")])
        self.control.apply("is_show_serial", True)
        self.assertIs(self.core.sender.show, True)

    def test_audio(self):
        with quiet():
            self.control.apply("is_use_audio", True)
        self.assertTrue(self.core.audio.is_running)
        self.assertEqual(self.core.settings.audio_device, "Capture A")
        with quiet():
            self.control.apply("audio_device", "Microphone")
            self.control.apply("audio_volume", 150)
            self.control.apply("is_audio_playback", False)
            self.control.apply("audio_output_device", "Speaker")
        capture = self.core.audio.capture
        self.assertEqual((capture.device_name, capture.volume, capture.is_playing), ("Microphone", 1.0, False))
        self.assertEqual(capture.output_device_name, "Speaker")
        with quiet():
            self.control.apply("audio_output_device", "Default")
            self.control.apply("is_use_audio", False)
        self.assertEqual(self.core.settings.audio_output_device, "")
        self.assertFalse(self.core.audio.is_running)

    def test_notifications_and_display(self):
        self.control.apply("is_discord_notification_end", True)
        self.control.apply("is_win_notification_start", 1)
        self.control.apply("is_show_value", True)
        self.control.apply("pos_dialogue_buttons", "3")
        self.assertIs(Command.isDiscordNotEnd, True)
        self.assertIs(Command.isWinNotStart, True)
        self.assertIs(Command.isSimilarity, True)
        self.assertEqual(Command.pos_dialogue_buttons, "3")
        self.assertIs(self.core.settings.is_discord_notification_end, True)

    def test_software_controller_layout(self):
        self.control.apply("software_controller_layout", "GameCube")
        self.assertEqual(self.core.calls, [("set_softcon_layout", "GameCube")])
        self.assertEqual(self.control.values()["software_controller_layout"], "GameCube")
        with self.assertRaises(SettingError):
            self.control.apply("software_controller_layout", "PlayStation")
        # Controller Simulator(大きいレイアウト)は、別の一覧から選ぶ
        self.control.apply("controller_layout", "3DS")
        self.assertEqual(self.core.calls[-1], ("set_simulator_layout", "3DS"))
        with self.assertRaises(SettingError):
            self.control.apply("controller_layout", "3DS (w/ TouchScreen)")

    def test_realtime_and_controller_device(self):
        self.control.apply("is_show_realtime", False)
        self.assertIs(self.core.settings.is_show_realtime, False)
        self.assertEqual(self.control.options()["controller_devices"], ["Auto"])
        with mock.patch.object(settings_control, "list_joystick_names", lambda: ["Pro Controller", "Pad"]), quiet():
            self.control.scan_controllers()
        devices = self.control.options()["controller_devices"]
        self.assertEqual((devices[0], len(devices)), ("Auto", 3))
        self.control.apply("controller_device", devices[2])
        self.assertEqual(self.core.settings.controller_device, devices[2])
        with self.assertRaises(SettingError):
            self.control.apply("controller_device", "  ")

        def fail():
            raise RuntimeError("pygame")

        with mock.patch.object(settings_control, "list_joystick_names", fail), quiet():
            self.control.scan_controllers()
        self.assertEqual(self.control.options()["controller_devices"], ["Auto"])

    def test_stdout_destination(self):
        self.control.apply("stdout_destination", "2")
        self.assertEqual(Command.stdout_destination, "2")
        (update,) = self.core.output.drain(lambda: 0)
        self.assertEqual((update.area, update.text), (2, "standard output destination is switched.\n"))

    def test_scan_follows_a_camera_whose_number_changed(self):
        self.core.settings.camera_id = 1
        with mock.patch.object(
            device_service, "list_cameras", lambda: ({0: "Capture B (path-b)", 1: "New (path-n)", "2": "Disable"}, {0: "path-b", 1: "path-n"})
        ):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.control.scan()
        self.assertEqual(self.core.settings.camera_id, 0)
        self.assertIn("No.1 から No.0", out.getvalue())
        self.assertIn("Scan Device: カメラ 2 台", out.getvalue())

    def test_scan_failure_keeps_the_previous_list(self):
        def fail():
            raise RuntimeError("no dll")

        with mock.patch.object(device_service, "list_cameras", fail), quiet():
            self.control.scan()
        self.assertEqual(len(self.control.options()["cameras"]), 3)

    def test_environment_without_camera_names(self):
        control = SettingsControl(self.core)
        with mock.patch.object(device_service, "list_cameras", lambda: None), quiet():
            control.scan()
        self.assertIsNone(control.options()["cameras"])
        control.apply("camera_source", 2)  # 番号をそのまま指定できる
        self.assertEqual(self.core.calls[-1], ("open_camera", 2, ""))


if __name__ == "__main__":
    unittest.main()
