#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/controller_setup_service.py のテスト(コントローラーをつながずに、状態を読む部分は代役を使う)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Commands import ControllerSetupSession  # noqa: E402
from Commands.ControllerProfile import ControllerProfileError, load_profile_file  # noqa: E402
from Commands.ControllerSetupSession import JoystickSnapshot  # noqa: E402
from Commands.Keys import Button  # noqa: E402
from services import controller_setup_service  # noqa: E402
from services.controller_setup_service import ControllerSetupService, SetupError  # noqa: E402

JOYSTICK = "Test Pad"
# 静止時の状態: ボタン16個、軸4本、ハット1個
REST = JoystickSnapshot(tuple([0] * 16), (0.0, 0.0, 0.0, 0.0), ((0, 0),))


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class FakeMonitor:
    """コントローラーの代わりに、テストが決めた状態を返す"""

    instances = []

    def __init__(self, device, expected_name):
        self.device = device
        self.expected_name = expected_name
        self.latest = None
        self.error = None
        self.started = False
        self.stopped = False
        FakeMonitor.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def pressed(button=None, axis=None, hat=None) -> JoystickSnapshot:
    buttons = list(REST.buttons)
    axes = list(REST.axes)
    hats = list(REST.hats)
    if button is not None:
        buttons[button] = 1
    if axis is not None:
        axes[axis[0]] = axis[1]
    if hat is not None:
        hats[0] = hat
    return JoystickSnapshot(tuple(buttons), tuple(axes), tuple(hats))


class ControllerSetupServiceTest(unittest.TestCase):
    def setUp(self):
        FakeMonitor.instances = []
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))
        self.stopped = []
        self.core = SimpleNamespace(
            commands=SimpleNamespace(is_running=False),
            settings=SimpleNamespace(controller_device="Auto"),
            settings_control=SimpleNamespace(controller_names=[]),
            stop_controller=lambda: self.stopped.append(True),
        )
        self.names = [JOYSTICK]
        directory = self.directory
        original = controller_setup_service.profile_file_for
        load = controller_setup_service.load_profiles
        patches = (
            (controller_setup_service, "list_joystick_names", lambda: list(self.names)),
            # プロファイルは、一時フォルダのもの(と、組み込みのもの)だけを使う
            (controller_setup_service, "load_profiles", lambda: load(directory)),
            (controller_setup_service, "profile_file_for", lambda name, profiles: original(name, profiles, directory)),
            # 静止時の状態を、すぐに確定させる
            (ControllerSetupSession, "BASELINE_STABLE_TIME", 0.0),
        )
        for target, name, value in patches:
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.states = []
        self.service = ControllerSetupService(self.core, FakeMonitor)
        self.addCleanup(self.service.close)

    def start(self):
        with quiet():
            state = self.service.start(self.states.append)
        self.monitor = FakeMonitor.instances[-1]
        return state

    def wait(self, predicate, seconds=3.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            state = self.service.state()
            if predicate(state):
                return state
            time.sleep(0.01)
        self.fail(f"the expected state did not come: {self.service.state()}")

    def feed(self, snapshot, predicate):
        self.monitor.latest = snapshot
        return self.wait(predicate)

    def press(self, snapshot):
        """入力を押して、離す(次の手順に進むまで待つ)"""
        index = self.service.state()["index"]
        self.feed(snapshot, lambda s: s.get("phase") in ("release", "done") or s.get("index", index) != index)
        return self.feed(REST, lambda s: s.get("phase") != "release")

    def test_start_prepares_and_then_shows_the_first_step(self):
        state = self.start()
        json.dumps(state)
        self.assertEqual((state["active"], state["phase"], state["exists"], state["total"]), (True, "preparing", False, 22))
        self.assertEqual(state["device"], "0: Test Pad")
        self.assertEqual(state["file"], "Test_Pad.json")
        self.assertTrue(self.monitor.started)
        self.assertEqual(self.stopped, [True])  # コントローラーでの操作は止める
        self.assertEqual(self.core.settings_control.controller_names, [JOYSTICK])
        state = self.feed(REST, lambda s: s["phase"] == "step")
        self.assertEqual((state["index"], state["label"], state["current"], state["can_back"]), (0, "A", "なし", False))
        self.assertIn("A", state["instruction"])

    def test_assign_skip_clear_back(self):
        self.start()
        self.feed(REST, lambda s: s["phase"] == "step")
        state = self.feed(pressed(button=3), lambda s: s["phase"] == "release")
        self.assertEqual(state["instruction"], "入力を離してください")
        self.assertEqual(state["inputs"], ["ボタン 3"])
        state = self.feed(REST, lambda s: s["phase"] == "step")
        self.assertEqual((state["index"], state["label"], state["changed"], state["can_back"]), (1, "B", True, True))
        self.assertEqual(self.service.skip()["index"], 2)
        self.assertEqual(self.service.clear()["index"], 3)
        state = self.service.back()
        self.assertEqual((state["index"], state["current"], state["current_changed"]), (2, "なし", True))
        state = self.service.back()
        state = self.service.back()
        self.assertEqual((state["index"], state["current"], state["can_back"]), (0, "ボタン 3", False))
        # 状態の変化は、知らせとして届いている
        self.assertTrue(any(s.get("phase") == "release" for s in self.states))

    def test_full_run_saves_a_profile(self):
        self.start()
        self.feed(REST, lambda s: s["phase"] == "step")
        for button in range(14):  # ボタン14個
            self.press(pressed(button=button))
        self.assertEqual(self.service.state()["label"], "十字キー 上")
        state = self.press(pressed(hat=(0, 1)))  # ハットなら、4方向まとめて割り当てる
        self.assertEqual(state["label"], "左スティック 左右")
        for axis in range(4):
            state = self.press(pressed(axis=(axis, 1.0 if axis != 1 else -1.0)))
        self.assertEqual(state["phase"], "done")
        self.assertEqual(len(state["summary"]), 22)
        self.assertEqual(state["summary"][0], {"label": "A", "value": "ボタン 0", "changed": True})
        self.assertEqual(state["summary"][14]["value"], "ハット 0")
        self.assertEqual(state["summary"][19]["value"], "軸 1 (反転)")
        self.assertEqual(state["duplicates"], [])
        with quiet():
            state = self.service.save()
        self.assertEqual(state, {"active": False})
        self.assertTrue(self.monitor.stopped)
        profile = load_profile_file(os.path.join(self.directory, "Test_Pad.json"))
        self.assertEqual((profile.name, profile.match, profile.hat_type, profile.hat_index), (JOYSTICK, [JOYSTICK], "hat", 0))
        self.assertEqual(profile.buttons[Button.A].index, 0)
        self.assertTrue(profile.sticks["ly"].invert)

    def test_duplicates_are_reported(self):
        self.start()
        self.feed(REST, lambda s: s["phase"] == "step")
        self.press(pressed(button=5))
        self.press(pressed(button=5))
        while self.service.state()["phase"] != "done":
            self.service.skip()
        self.assertEqual(self.service.state()["duplicates"], ["ボタン 5: A, B"])

    def test_save_is_refused_before_the_end_and_cancel_keeps_no_file(self):
        self.start()
        self.feed(REST, lambda s: s["phase"] == "step")
        with self.assertRaises(SetupError):
            self.service.save()
        self.assertEqual(self.service.cancel(), {"active": False})
        self.assertEqual(os.listdir(self.directory), [])
        self.assertTrue(self.monitor.stopped)
        for call in (self.service.back, self.service.skip, self.service.clear, self.service.save):
            with self.assertRaises(SetupError):
                call()

    def test_start_errors(self):
        self.core.commands.is_running = True
        with self.assertRaises(SetupError):
            self.service.start()
        self.core.commands.is_running = False
        self.names = []
        with self.assertRaises(SetupError), quiet():
            self.service.start()
        self.assertFalse(self.service.active)

        def fail():
            raise RuntimeError("pygame")

        with mock.patch.object(controller_setup_service, "list_joystick_names", fail), self.assertRaises(SetupError), quiet():
            self.service.start()

    def test_disconnect_ends_the_setup(self):
        self.start()
        self.feed(REST, lambda s: s["phase"] == "step")
        self.monitor.error = "コントローラーが切断されました"
        deadline = time.time() + 3
        while self.service.active and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.service.active)
        self.assertEqual((self.states[-1]["active"], self.states[-1]["error"]), (False, "コントローラーが切断されました"))

    def test_existing_file_is_updated(self):
        self.start()
        self.feed(REST, lambda s: s["phase"] == "step")
        self.press(pressed(button=1))
        while self.service.state()["phase"] != "done":
            self.service.skip()
        with quiet():
            self.service.save()
        # 2回目: 保存したファイルを元にして始まる
        state = self.start()
        self.assertTrue(state["exists"])
        state = self.feed(REST, lambda s: s["phase"] == "step")
        self.assertEqual((state["current"], state["current_changed"]), ("ボタン 1", False))

    def test_modules_do_not_import_tkinter(self):
        for module in (controller_setup_service, ControllerSetupSession):
            with io.open(module.__file__, encoding="utf-8") as file:
                source = file.read()
            self.assertNotIn("import tkinter", source)
            self.assertNotIn("from tkinter", source)
        self.assertIs(ControllerProfileError.__mro__[1], ValueError)


if __name__ == "__main__":
    unittest.main()
