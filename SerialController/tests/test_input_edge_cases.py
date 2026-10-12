#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
入力の送り方のうち、書き間違いがあった所(4 か所)の動きを確かめるテスト。

どれも、このアプリの中からは通らない条件でだけ違いが出る(スクリプトが直接呼んだ場合に限る)。
4 か所(show_input の条件、タッチを離す判定、スティックの反転、十字キーのコマンドの isRunning)とも直してあり、
直した後の動きを確かめる。show_input は、スティックの印(行の下位 2 ビット)をボタンとして表示していた点も直してある。

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
from Commands import UnitCommand  # noqa: E402
from Commands.Keys import Button, Direction, Hat, KeyPress, SendFormat, Touchscreen  # noqa: E402
from Commands.Sender import Sender  # noqa: E402


class EdgeCase(unittest.TestCase):
    def setUp(self):
        self.original_format = KeyPress.serial_data_format_name
        self.addCleanup(lambda: setattr(KeyPress, "serial_data_format_name", self.original_format))

    def sender(self, format_name="Default"):
        KeyPress.serial_data_format_name = format_name
        with contextlib.redirect_stdout(io.StringIO()):
            sender = Sender(False)
        self.log = []
        sender.ser = transport_scenarios.FakeSerial(self.log)
        return sender

    def rows(self):
        return [entry.split(" ", 1)[1] for entry in self.log]


class ShowInputTest(EdgeCase):
    """Sender.show_input: Default の形式の行から、self.press(...) の形の文を表示する"""

    def shown(self, row):
        sender = self.sender()
        sender.time_bef = sender.time_aft = 0.0
        sender._logger = mock.Mock()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            sender.show_input(row.split(" "))
        return output.getvalue().strip()

    def test_rows_that_are_shown_the_same_either_way(self):
        # 両方のスティックの印がある行(このアプリが、ボタンを押したときに作る行)。
        # 印は、ボタンとしては表示しない(以前は、印の 1 つが Stick.LEFT として、ボタンと一緒に表示されていた)
        self.assertEqual(self.shown("0x0013 8 80 80 80 80"), "self.press(Button.A, duration=0.00)")
        self.assertEqual(self.shown("0x001b 8 80 80 80 80"), "self.press([Button.B, Button.A], duration=0.00)")
        self.assertEqual(self.shown("0x0003 0 80 80 80 80"), "self.press(Hat.TOP, duration=0.00)")
        self.assertEqual(self.shown("0x0003 8 80 80 80 80"), "")
        # 左の印だけの行と、印のない行
        self.assertEqual(self.shown("0x0012 8 80 80 80 80"), "self.press(Button.A, duration=0.00)")
        self.assertEqual(self.shown("0x001a 8 80 80 80 80"), "self.press([Button.B, Button.A], duration=0.00)")
        self.assertEqual(self.shown("0x0010 8 80 80 80 80"), "self.press(Button.A, duration=0.00)")

    def test_rows_with_only_the_right_stick_flag(self):
        # 右の印だけがあり、スティックは中央の行は、左の印だけの行と同じように表示する
        # (以前は、条件が `useRStick and useRStick` で、「両方の印がある行」と同じ扱いになっていた。
        #  ボタン 1 つは表示されず、2 つのときはリストの [ ] が付かなかった)
        self.assertEqual(self.shown("0x0011 8 80 80 80 80"), "self.press(Button.A, duration=0.00)")
        self.assertEqual(self.shown("0x0001 0 80 80 80 80"), "self.press(Hat.TOP, duration=0.00)")
        self.assertEqual(self.shown("0x0019 8 80 80 80 80"), "self.press([Button.B, Button.A], duration=0.00)")
        self.assertEqual(self.shown("0x0011 0 80 80 80 80"), "self.press([Button.A, Hat.TOP], duration=0.00)")

    def test_tilted_sticks_are_shown_with_their_own_names(self):
        # 倒しているスティックは、印の付き方に関わらず、そのスティックの名前で表示する
        # (以前は、両方の印がある行や、印と食い違う行で、左を Stick.RIGHT と表示したり、ボタンを Direction の中に表示したりしていた)
        left, right = "Direction(Stick.LEFT, 0)", "Direction(Stick.RIGHT, 90)"
        self.assertEqual(self.shown("0x0002 8 ff 80 80 80"), f"self.press({left}, duration=0.00)")
        self.assertEqual(self.shown("0x0003 8 ff 80 80 80"), f"self.press({left}, duration=0.00)")
        self.assertEqual(self.shown("0x0001 8 ff 80 80 80"), f"self.press({left}, duration=0.00)")
        self.assertEqual(self.shown("0x0001 8 80 80 80 0"), f"self.press({right}, duration=0.00)")
        self.assertEqual(self.shown("0x0013 8 ff 80 80 80"), f"self.press([Button.A, {left}], duration=0.00)")
        # 両方を倒しているときは、ボタンも一緒に表示する(以前は、ボタンが抜けるか、エラーになっていた)
        self.assertEqual(self.shown("0x0003 8 ff 80 80 0"), f"self.press([{right}, {left}], duration=0.00)")
        self.assertEqual(self.shown("0x0013 0 ff 80 80 0"),
                         f"self.press([Button.A, Hat.TOP, {right}, {left}], duration=0.00)")
        self.assertEqual(self.shown("0x0001 8 ff 80 80 0"), f"self.press([{right}, {left}], duration=0.00)")

    def test_held_sticks_are_shown_with_rows_without_stick_values(self):
        sender = self.sender()
        sender.time_bef = sender.time_aft = 0.0
        sender._logger = mock.Mock()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            sender.show_input("0x0002 8 ff 80".split(" "))  # 左を倒す(覚える)
            sender.show_input("0x0010 8".split(" "))  # スティックの値のない行: A と、倒したままの左
            sender.show_input("0x0000 8".split(" "))  # 何も押していない行: 倒したままの左だけ
            sender.show_input("0x0002 8 80 80".split(" "))  # 左を中央に戻す
            sender.show_input("0x0010 8".split(" "))  # A だけ
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "self.press(Direction(Stick.LEFT, 0), duration=0.00)",
                "self.press([Button.A, Direction(Stick.LEFT, 0)], duration=0.00)",
                "self.press(Direction(Stick.LEFT, 0), duration=0.00)",
                "self.press(Button.A, duration=0.00)",
            ],
        )
        sender._logger.error.assert_not_called()

    def test_it_is_not_called_by_the_inputs_of_this_application(self):
        sender = self.sender()
        with mock.patch.object(Sender, "show_input") as show_input, contextlib.redirect_stdout(io.StringIO()):
            keys = KeyPress(sender)
            for item in (Button.A, [Button.A, Button.B], Hat.TOP, Direction.UP, [Button.X, Direction.R_UP]):
                keys.input(item)
                keys.inputEnd(item)
            keys.hold(Button.B)
            keys.holdEnd(Button.B)
        self.assertGreater(len(self.log), 10)
        show_input.assert_not_called()


class TouchscreenReleaseTest(EdgeCase):
    """KeyPress.inputEnd: タッチを離す条件"""

    TOUCH = "ab 00 00 08 80 80 80 80 64 00 32"
    RELEASED = "ab 00 00 08 80 80 80 80 00 00 00"

    def run_keys(self, scenario):
        sender = self.sender("Qingpi")
        with contextlib.redirect_stdout(io.StringIO()):
            scenario(KeyPress(sender))
        return self.rows()

    def test_default_arguments_release_the_touch(self):
        touch = Touchscreen(100, 50)
        self.assertEqual(self.run_keys(lambda k: (k.input(touch), k.inputEnd(touch))), [self.TOUCH, self.RELEASED])
        # ホールドしていないタッチは、ほかのボタンを離すときにも離れる
        self.assertEqual(self.run_keys(lambda k: (k.input(touch), k.inputEnd(Button.A))), [self.TOUCH, self.RELEASED])
        # ホールド中のタッチは、ほかのボタンを離しても残り、holdEnd で離れる
        rows = self.run_keys(lambda k: (k.hold(touch), k.input(Button.A), k.inputEnd(Button.A), k.holdEnd(touch)))
        self.assertEqual(rows, [self.TOUCH, "ab 04 00 08 80 80 80 80 64 00 32", self.TOUCH, self.RELEASED])

    def test_unset_touchscreen_false_releases_the_touch_when_it_is_in_the_list(self):
        touch = Touchscreen(100, 50)
        # unset_Touchscreen=False でも、離す一覧にタッチがあれば離す
        # (以前は、判定の式が常に False で、タッチが離れなかった)
        self.assertEqual(
            self.run_keys(lambda k: (k.input(touch), k.inputEnd(touch, unset_Touchscreen=False))),
            [self.TOUCH, self.RELEASED],
        )
        self.assertEqual(
            self.run_keys(lambda k: (k.input([Button.A, touch]), k.inputEnd([Button.A, touch], unset_Touchscreen=False))),
            ["ab 04 00 08 80 80 80 80 64 00 32", self.RELEASED],
        )
        self.assertEqual(
            self.run_keys(lambda k: (k.hold(touch), k.inputEnd(touch, unset_Touchscreen=False))),
            [self.TOUCH, self.RELEASED],
        )
        # 一覧にタッチがなければ、タッチは残る
        self.assertEqual(
            self.run_keys(lambda k: (k.input([Button.A, touch]), k.inputEnd(Button.A, unset_Touchscreen=False))),
            ["ab 04 00 08 80 80 80 80 64 00 32", self.TOUCH],
        )


class ReversedDirectionTest(EdgeCase):
    """SendFormat.setAnyDirection: x_reverse / y_reverse を付けたときの、変化の印"""

    @staticmethod
    def lines(steps):
        encoder = SendFormat()
        result = []
        for direction, x_reverse, y_reverse in steps:
            encoder.setAnyDirection([direction], x_reverse, y_reverse)
            result.append(encoder.convert2str())
        return result

    def test_without_reverse(self):
        # 同じ向きを続けて入れると、2 回目はスティックを付けない
        self.assertEqual(self.lines([(Direction.RIGHT, False, False)] * 2), ["0x0002 8 ff 80", "0x0000 8"])
        self.assertEqual(
            self.lines([(Direction.RIGHT, False, False), (Direction.LEFT, False, False)]),
            ["0x0002 8 ff 80", "0x0002 8 0 80"],
        )

    def test_with_reverse_the_change_is_judged_by_the_value_after_reversing(self):
        # 変化の判定は、反転した後の値(実際に入れる値)で行う
        # (以前は、反転する前の値で判定していて、下の 2 つが逆になっていた)
        # 同じ向きを続けて入れると、2 回目はスティックを付けない
        self.assertEqual(self.lines([(Direction.RIGHT, True, False)] * 2), ["0x0002 8 0 80", "0x0000 8"])
        self.assertEqual(self.lines([(Direction.UP, False, True)] * 2), ["0x0002 8 80 ff", "0x0000 8"])
        self.assertEqual(self.lines([(Direction.R_RIGHT, True, False)] * 2), ["0x0001 8 0 80", "0x0000 8"])
        # 逆の向きに変えると、2 回目もスティックを付ける
        self.assertEqual(
            self.lines([(Direction.RIGHT, True, False), (Direction.LEFT, True, False)]),
            ["0x0002 8 0 80", "0x0002 8 ff 80"],
        )
        self.assertEqual(
            self.lines([(Direction.UP, False, True), (Direction.DOWN, False, True)]),
            ["0x0002 8 80 ff", "0x0002 8 80 0"],
        )
        # 反転なしの「右」と、X 反転の「左」は、入れる値が同じなので、変化なし
        self.assertEqual(
            self.lines([(Direction.RIGHT, False, False), (Direction.LEFT, True, False)]),
            ["0x0002 8 ff 80", "0x0000 8"],
        )

    def test_inputs_of_this_application_do_not_depend_on_the_flags(self):
        # コマンドの入力は、反転を使わない。Default の形式では、変化の印は、送る直前に、前に送った状態と比べて付け直す
        sender = self.sender()
        with contextlib.redirect_stdout(io.StringIO()):
            keys = KeyPress(sender)
            keys.input(Direction.RIGHT)
            keys.input(Direction.RIGHT)
            keys.input(Direction.UP)
            keys.inputEnd(Direction.UP)
        # 2 回目の「右」は、前に送った状態と同じなので、スティックを付けない行になる
        self.assertEqual(self.rows(), ["0x0003 8 ff 80 80 80", "0x0000 8", "0x0002 8 80 0", "0x0002 8 80 80"])


class UnitCommandTest(EdgeCase):
    """UnitCommand: 画面のボタンを 1 回押すコマンド"""

    def run_command(self, command_class):
        sender = self.sender()
        command = command_class()
        with mock.patch.object(UnitCommand, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            command.start(sender)
        return command

    def test_buttons_finish(self):
        command = self.run_command(UnitCommand.A)
        self.assertEqual(self.rows(), ["0x0013 8 80 80 80 80", "0x0000 8"])
        self.assertFalse(command.isRunning)
        self.assertIsNone(command.key)

    def test_hat_commands_send_the_same_way_and_finish(self):
        commands = (
            (UnitCommand.UP, 0), (UnitCommand.UP_RIGHT, 1), (UnitCommand.RIGHT, 2), (UnitCommand.DOWN_RIGHT, 3),
            (UnitCommand.DOWN, 4), (UnitCommand.DOWN_LEFT, 5), (UnitCommand.LEFT, 6), (UnitCommand.UP_LEFT, 7),
        )
        for command_class, hat in commands:
            with self.subTest(command=command_class.__name__):
                command = self.run_command(command_class)
                # 送るデータは、押して離す形になっている
                self.assertEqual(self.rows(), [f"0x0003 {hat} 80 80 80 80", "0x0000 8"])
                self.assertIsNone(command.key)
                # 終わったら、ボタンのコマンドと同じく、isRunning は False(以前は、True のままだった)
                self.assertFalse(command.isRunning)


if __name__ == "__main__":
    unittest.main()
