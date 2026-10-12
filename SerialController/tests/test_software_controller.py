#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software-Controller のレイアウトの取り出し(ControllerLayouts.describe_layout)と、
入力(services/software_controller.py)のテスト。画面を起動せずに実行できる

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERIAL_CONTROLLER_DIR)

import ControllerColors  # noqa: E402
import ControllerLayouts  # noqa: E402
from Commands.Keys import Button, Direction, Hat, Stick, Touchscreen  # noqa: E402
from services import software_controller  # noqa: E402
from services.software_controller import SoftwareController, SoftwareControllerError  # noqa: E402


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class DescribeLayoutTest(unittest.TestCase):
    def test_every_layout_can_be_sent_as_json(self):
        for name in ControllerLayouts.COMPACT_LAYOUTS:
            layout = ControllerLayouts.describe_layout(name)
            json.dumps(layout)
            self.assertEqual((layout["name"], layout["width"], layout["height"]), (name, 380, 190))
            self.assertTrue(layout["hold"], name)
            self.assertTrue(layout["shapes"], name)
            kinds = {shape["type"] for shape in layout["shapes"]}
            self.assertLessEqual(kinds, {"rect", "oval", "roundrect", "polygon", "text", "image"}, name)
            # HOLD ボタンと、すべてのボタン・スティックに、押せる図形がある
            tags = {shape["tags"][0] for shape in layout["shapes"] if shape["tags"]}
            self.assertIn("hold_toggle", tags)
            self.assertLessEqual(set(layout["buttons"]) | set(layout["sticks"]), tags, name)

    def test_switch_layout(self):
        layout = ControllerLayouts.describe_layout("Switch (Joy-Con)")
        self.assertEqual(layout["buttons"]["btn_a"], {"kind": "button", "name": "A"})
        self.assertEqual(layout["buttons"]["hat_TOP_LEFT"], {"kind": "hat", "name": "TOP_LEFT"})
        self.assertEqual(len([tag for tag in layout["buttons"] if tag.startswith("hat_")]), 8)
        self.assertEqual(sorted(layout["sticks"]), ["stick_left", "stick_right"])
        stick = layout["sticks"]["stick_left"]
        self.assertEqual((stick["stick"], stick["center"], stick["range"], stick["knob_radius"]), ("LEFT", [46, 86], 18, 15))
        knob = layout["shapes"][stick["knob"]]
        self.assertEqual((knob["type"], knob["coords"]), ("oval", [31.0, 71.0, 61.0, 101.0]))
        self.assertEqual(layout["shapes"][stick["label"]]["text"], "L")
        self.assertIsNone(layout["touch"])
        zl = next(shape for shape in layout["shapes"] if shape["tags"][:1] == ["btn_zl"])
        self.assertEqual((zl["type"], zl["coords"], zl["radius"]), ("roundrect", [6.0, 4.0, 66.0, 22.0], 6))

    def test_touchscreen_layout(self):
        layout = ControllerLayouts.describe_layout("3DS (w/ TouchScreen)")
        touch = layout["touch"]
        self.assertEqual(touch["size"], [200, 150])
        self.assertEqual(layout["shapes"][touch["image"]]["type"], "image")
        self.assertEqual(layout["shapes"][touch["text"]]["text"], "Touch Screen")
        self.assertEqual(layout["touch_size"], [320, 240])

    def test_old_and_unknown_names(self):
        self.assertEqual(ControllerLayouts.describe_layout("Switch")["name"], "Switch (Joy-Con)")
        self.assertEqual(ControllerLayouts.describe_layout("3DS")["name"], "3DS (w/o TouchScreen)")
        self.assertEqual(ControllerLayouts.describe_layout("no such layout")["name"], "Switch (Joy-Con)")
        self.assertEqual(software_controller.normalize_layout_name("DS"), "DS (w/o TouchScreen)")
        self.assertEqual(software_controller.layout_names(), list(ControllerLayouts.COMPACT_LAYOUTS))

    def test_body_colors_follow_the_settings(self):
        saved = ControllerColors.settings_texts()
        self.addCleanup(lambda: ControllerColors.load_settings(saved))
        default = ControllerLayouts.describe_layout("Switch (Pro Controller)")["background"]
        layout = ControllerLayouts.describe_layout("Switch (Pro Controller)", colors={"body": "#123456"})
        self.assertEqual(layout["background"].lower(), "#123456")
        self.assertNotEqual(default.lower(), "#123456")

    def test_layouts_can_be_read_without_tkinter(self):
        code = (
            "import sys\n"
            "import ControllerLayouts, services.software_controller\n"
            "ControllerLayouts.describe_layout('3DS (w/ TouchScreen)')\n"
            "sys.stderr.write('TKINTER=' + str('tkinter' in sys.modules))\n"
        )
        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", code], cwd=SERIAL_CONTROLLER_DIR, capture_output=True, timeout=120
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace")[-500:])
        self.assertIn(b"TKINTER=False", result.stderr)


class FakeKeys:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda value: self.calls.append((name, value))


class SoftwareControllerTest(unittest.TestCase):
    def setUp(self):
        self.keys = FakeKeys()
        self.softcon = SoftwareController(self.keys)
        self.softcon.set_layout("Switch (Joy-Con)")

    def names(self):
        out = []
        for name, value in self.keys.calls:
            if isinstance(value, list):
                out.append((name, value[0]))
            elif isinstance(value, Direction):
                out.append((name, value.stick, (value.x, value.y)))
            elif isinstance(value, Touchscreen):
                out.append((name, "touch", (value.x, value.y)))
        return out

    def test_press_and_release(self):
        self.softcon.press("btn_a")
        self.assertFalse(self.softcon.is_idle())
        self.softcon.release("btn_a")
        self.softcon.press("hat_TOP")
        self.softcon.release("hat_TOP")
        self.assertEqual(
            self.names(), [("input", Button.A), ("inputEnd", Button.A), ("input", Hat.TOP), ("inputEnd", Hat.TOP)]
        )
        self.assertIs(type(self.keys.calls[2][1][0]), Hat)
        self.assertTrue(self.softcon.is_idle())

    def test_hold_keeps_the_button_until_hold_end(self):
        self.softcon.press("btn_b")
        self.softcon.hold("btn_b")  # 押したまま固定する
        self.softcon.hold("btn_x")  # 右クリックでの固定(押さずに固定する)
        self.softcon.hold_end("btn_b")
        self.softcon.hold_end("btn_b")  # 固定していない場合は何もしない
        self.assertEqual(
            self.names(), [("input", Button.B), ("hold", Button.B), ("hold", Button.X), ("holdEnd", Button.B)]
        )
        self.assertFalse(self.softcon.is_idle())

    def test_only_one_hat_direction_is_held(self):
        self.softcon.hold("hat_TOP")
        self.softcon.hold("hat_RIGHT")
        self.softcon.hold("btn_a")
        self.assertEqual(
            self.names(), [("hold", Hat.TOP), ("holdEnd", Hat.TOP), ("hold", Hat.RIGHT), ("hold", Button.A)]
        )

    def test_stick(self):
        with quiet():
            self.softcon.tilt("stick_left", 90, 1.0)
            self.softcon.tilt("stick_right", 0, 5)  # 大きさは 1 までに収める
            self.softcon.tilt("stick_right", 0, 0.05)  # 少ししか倒していない場合は、倒していないものとする
            self.softcon.center("stick_left")
        calls = self.names()
        self.assertEqual([(c[0], c[1]) for c in calls], [("input", Stick.LEFT), ("input", Stick.RIGHT), ("input", Stick.RIGHT), ("input", Stick.LEFT)])
        self.assertEqual(calls[2][2], (128, 127))
        self.assertEqual(calls[3][2], (128, 127))
        self.assertNotEqual(calls[0][2], (128, 127))
        self.assertTrue(self.softcon.is_idle())

    def test_unknown_parts_are_refused(self):
        for call in (lambda: self.softcon.press("btn_start"), lambda: self.softcon.tilt("stick_pad", 0, 1), lambda: self.softcon.touch(10, 10)):
            with self.assertRaises(SoftwareControllerError):
                call()
        self.assertEqual(self.keys.calls, [])

    def test_touch(self):
        self.softcon.set_layout("3DS (w/ TouchScreen)")
        self.softcon.touch_end()  # 押していない場合は何もしない
        self.softcon.touch(160.4, 120)
        self.softcon.touch(-5, 999)  # 範囲に収める((0, 0) は離した状態を表すので、1以上にする)
        self.softcon.touch_end()
        self.assertEqual(
            self.names(), [("input", "touch", (160, 120)), ("input", "touch", (1, 240)), ("inputEnd", "touch", (0, 0))]
        )

    def test_release_all(self):
        with quiet():
            self.softcon.press("btn_a")
            self.softcon.hold("btn_b")
            self.softcon.tilt("stick_left", 0, 1)
            self.softcon.release_all()
            self.softcon.release_all()
        self.assertEqual([c[:2] for c in self.names()[3:]], [("holdEnd", Button.B), ("inputEnd", Button.A), ("input", Stick.LEFT)])
        self.assertTrue(self.softcon.is_idle())

    def test_large_layouts(self):
        self.assertEqual(software_controller.layout_names(large=True), ["Switch (Joy-Con)", "Switch (Pro Controller)", "3DS", "DS", "GameCube"])
        for name in ControllerLayouts.LARGE_LAYOUTS:
            layout = ControllerLayouts.describe_layout(name, large=True)
            json.dumps(layout)
            self.assertEqual((layout["name"], layout["width"], layout["height"]), (name, 600, 300))
            self.assertFalse(layout["hold"], name)  # 大きいレイアウトには、押しっぱなしの固定は無い
        self.assertEqual(ControllerLayouts.describe_layout("3DS", large=True)["touch"]["size"], [320, 240])
        self.assertEqual(ControllerLayouts.describe_layout("unknown", large=True)["name"], "Switch (Joy-Con)")
        simulator = SoftwareController(self.keys, large=True)
        self.assertEqual(simulator.set_layout("3DS")["name"], "3DS")
        simulator.press("btn_start")
        simulator.touch(100, 50)
        simulator.release_all()
        self.assertEqual([c[0] for c in self.names()], ["input", "input", "inputEnd", "inputEnd"])

    def test_changing_the_layout_releases_the_inputs(self):
        self.softcon.hold("btn_zl")
        layout = self.softcon.set_layout("DS")
        self.assertEqual(layout["name"], "DS (w/o TouchScreen)")
        self.assertEqual(self.names()[-1], ("holdEnd", Button.ZL))
        with self.assertRaises(SoftwareControllerError):
            self.softcon.press("btn_zl")
        self.softcon.press("btn_start")


if __name__ == "__main__":
    unittest.main()
