#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キーボードでの手動操作(Keyboard.py)のテスト: Alt を押している間は、ゲーム機に送らない
(Alt + F などは、メニューを開く操作に使うため)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pynput.keyboard import Key, KeyCode  # noqa: E402

from Commands.Keys import Button, Direction  # noqa: E402
from Keyboard import SwitchKeyboardController  # noqa: E402


class FakeKeyPress:
    """入力の送り先の代役(呼ばれた内容を記録する)"""

    def __init__(self):
        self.calls = []

    def input(self, buttons, *args, **kwargs):
        self.calls.append(("input", buttons))

    def inputEnd(self, buttons, *args, **kwargs):
        self.calls.append(("inputEnd", buttons))

    def release(self):
        self.calls.append(("release",))

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name,))


def char(character: str, vk: int | None = None) -> KeyCode:
    return KeyCode(vk=vk, char=character)


class MenuKeyTestMixin:
    """メニューを操作している間かどうかを、テストから決められるようにする"""

    def useMenuState(self):
        self.menu_open = False
        original = SwitchKeyboardController._menuIsOpen
        SwitchKeyboardController._menuIsOpen = staticmethod(lambda: self.menu_open)
        self.addCleanup(lambda: setattr(SwitchKeyboardController, "_menuIsOpen", staticmethod(original)))


class AltKeyTest(unittest.TestCase):
    def setUp(self):
        self.keys = FakeKeyPress()
        self.keyboard = SwitchKeyboardController(self.keys)
        # 設定ファイルによらず、決まった対応にする
        self.keyboard.key_map = {"a": Button.A, "f": Button.B}
        self.keyboard.key_map_B = dict(self.keyboard.key_map)
        self.keyboard.key_map_D = {}
        self.keyboard.key_map_H = {}

    def sent(self):
        return [call for call in self.keys.calls if call[0] in ("input", "inputEnd")]

    def test_keys_are_sent_without_alt(self):
        self.keyboard.on_press(char("a"))
        self.keyboard.on_release(char("a"))
        self.assertEqual(self.sent(), [("input", Button.A), ("inputEnd", Button.A)])

    def test_keys_pressed_while_alt_is_down_are_not_sent(self):
        for alt in (Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr):
            with self.subTest(alt=alt):
                self.keys.calls.clear()
                self.keyboard.on_press(alt)
                self.keyboard.on_press(char("f"))
                self.keyboard.on_release(char("f"))
                self.keyboard.on_release(alt)
                self.assertEqual(self.sent(), [])
                # Alt を離した後は、これまでどおり送る
                self.keyboard.on_press(char("f"))
                self.keyboard.on_release(char("f"))
                self.assertEqual(self.sent(), [("input", Button.B), ("inputEnd", Button.B)])

    def test_a_key_held_past_alt_is_ignored_until_it_is_released(self):
        self.keyboard.on_press(Key.alt_l)
        self.keyboard.on_press(char("f", vk=70))
        self.keyboard.on_release(Key.alt_l)
        # キーを押し続けている間の繰り返し(Alt を離した後に届く)
        self.keyboard.on_press(char("f", vk=70))
        self.keyboard.on_press(char("f", vk=70))
        self.keyboard.on_release(char("f", vk=70))
        self.assertEqual(self.sent(), [])
        self.keyboard.on_press(char("f", vk=70))
        self.assertEqual(self.sent(), [("input", Button.B)])

    def test_the_same_key_is_matched_even_if_alt_changes_its_character(self):
        # Alt を押している間は、文字が大文字になる・取れない、という届き方がある
        self.keyboard.on_press(Key.alt_l)
        self.keyboard.on_press(char("F"))
        self.keyboard.on_release(Key.alt_l)
        self.keyboard.on_press(char("f"))
        self.assertEqual(self.sent(), [])
        self.keyboard.on_release(char("f"))
        self.keyboard.on_press(char("f"))
        self.assertEqual(self.sent(), [("input", Button.B)])

    def test_a_key_held_before_alt_is_still_released(self):
        self.keyboard.on_press(char("a"))
        self.keyboard.on_press(Key.alt_l)
        self.keyboard.on_release(char("a"))
        self.keyboard.on_release(Key.alt_l)
        self.assertEqual(self.sent(), [("input", Button.A), ("inputEnd", Button.A)])

    def test_alt_assigned_to_a_button_is_sent_as_before(self):
        self.keyboard.key_map[Key.alt_l] = Button.X
        self.keyboard.key_map_B[Key.alt_l] = Button.X
        self.keyboard.on_press(Key.alt_l)
        self.keyboard.on_press(char("a"))
        self.assertEqual(self.sent(), [("input", Button.X), ("input", Button.A)])

    def test_the_state_is_cleared_when_listening_stops(self):
        self.keyboard.on_press(Key.alt_l)
        self.keyboard._releaseHolding()
        self.keyboard.on_press(char("a"))
        self.assertEqual(self.sent(), [("input", Button.A)])


class CtrlKeyTest(AltKeyTest):
    """Ctrl も、Alt と同じ扱い(Ctrl + F、Ctrl + C などの、画面の操作に使うため)"""

    def test_ctrl_f_is_not_sent_and_not_logged_as_an_error(self):
        # Ctrl を押している間の文字のキーは、制御文字("\x06" など)として届く
        with self.assertNoLogs(self.keyboard._logger, "ERROR"):
            self.keyboard.on_press(Key.ctrl_l)
            self.keyboard.on_press(char("\x06", vk=70))
            self.keyboard.on_release(char("\x06", vk=70))
            self.keyboard.on_release(Key.ctrl_l)
        self.assertEqual(self.sent(), [])

    def test_ctrl_c_is_not_logged_as_an_error(self):
        with self.assertNoLogs(self.keyboard._logger, "ERROR"):
            self.keyboard.on_press(Key.ctrl_r)
            self.keyboard.on_press(char("\x03", vk=67))
            self.keyboard.on_release(char("\x03", vk=67))
            self.keyboard.on_release(Key.ctrl_r)
        self.assertEqual(self.sent(), [])

    def test_a_key_held_past_ctrl_is_ignored_until_it_is_released(self):
        self.keyboard.on_press(Key.ctrl_l)
        self.keyboard.on_press(char("\x06", vk=70))
        self.keyboard.on_release(Key.ctrl_l)
        # Ctrl を先に離した後の、押し続けている間の繰り返し(ふつうの文字として届く)
        self.keyboard.on_press(char("f", vk=70))
        self.keyboard.on_release(char("f", vk=70))
        self.assertEqual(self.sent(), [])
        self.keyboard.on_press(char("f", vk=70))
        self.assertEqual(self.sent(), [("input", Button.B)])

    def test_keys_work_again_after_ctrl(self):
        self.keyboard.on_press(Key.ctrl_l)
        self.keyboard.on_release(Key.ctrl_l)
        self.keyboard.on_press(char("a", vk=65))
        self.keyboard.on_release(char("a", vk=65))
        self.assertEqual(self.sent(), [("input", Button.A), ("inputEnd", Button.A)])

    def test_ctrl_assigned_to_a_button_is_sent_as_before(self):
        self.keyboard.key_map[Key.ctrl_l] = Button.X
        self.keyboard.key_map_B[Key.ctrl_l] = Button.X
        self.keyboard.on_press(Key.ctrl_l)
        self.keyboard.on_press(char("a", vk=65))
        self.assertEqual(self.sent(), [("input", Button.X), ("input", Button.A)])


class SuspendTest(AltKeyTest):
    """入力欄に文字を打っている間(suspend 〜 resume)は、キーをゲーム機に送らない"""

    def setUp(self):
        super().setUp()
        self.addCleanup(SwitchKeyboardController.resume)

    def test_keys_are_not_sent_while_suspended(self):
        self.keyboard.suspend()
        self.keyboard.on_press(char("a", vk=65))
        self.keyboard.on_release(char("a", vk=65))
        self.assertEqual(self.sent(), [])
        SwitchKeyboardController.resume()
        self.keyboard.on_press(char("a", vk=65))
        self.assertEqual(self.sent(), [("input", Button.A)])

    def test_held_keys_are_released_when_suspended(self):
        self.keyboard.on_press(char("a", vk=65))
        self.keyboard.suspend()
        self.assertIn(("release",), self.keys.calls)
        self.assertEqual(self.keyboard.holding, [])
        # 押したままだったキーを、後で離しても、何も送らない
        before = len(self.keys.calls)
        self.keyboard.on_release(char("a", vk=65))
        self.assertEqual(len(self.keys.calls), before)

    def test_a_key_held_past_resume_is_ignored_until_it_is_released(self):
        self.keyboard.suspend()
        self.keyboard.on_press(char("a", vk=65))
        SwitchKeyboardController.resume()
        # 打ち終わった後の、押し続けている間の繰り返し
        self.keyboard.on_press(char("a", vk=65))
        self.assertEqual(self.sent(), [])
        self.keyboard.on_release(char("a", vk=65))
        self.keyboard.on_press(char("a", vk=65))
        self.assertEqual(self.sent(), [("input", Button.A)])

    def test_a_new_listener_stays_suspended(self):
        self.keyboard.suspend()
        other = SwitchKeyboardController(self.keys)
        other.key_map = dict(self.keyboard.key_map)
        other.on_press(char("a", vk=65))
        self.assertEqual(self.sent(), [])

    def test_unassigned_keys_do_nothing_while_suspended(self):
        self.keyboard.suspend()
        with self.assertNoLogs(self.keyboard._logger, "ERROR"):
            self.keyboard.on_press(Key.enter)
            self.keyboard.on_release(Key.enter)
            self.keyboard.on_press(char("z", vk=90))
            self.keyboard.on_release(char("z", vk=90))
        self.assertEqual(self.sent(), [])


class UnassignedKeyTest(AltKeyTest):
    """対応のないキーは、何も送らず、エラーのログも出さない"""

    def setUp(self):
        super().setUp()
        self.addCleanup(SwitchKeyboardController.resume)

    def test_unassigned_character_keys_are_silent(self):
        with self.assertNoLogs(self.keyboard._logger, "ERROR"):
            for key in (char("z", vk=90), char("", vk=70), char(""), KeyCode(vk=255)):
                self.keyboard.on_press(key)
                self.keyboard.on_release(key)
        self.assertEqual(self.sent(), [])

    def test_ctrl_f_that_opens_the_search_box_is_silent(self):
        # Ctrl + F を押す → 検索の欄が開いて、手動操作が止まる → F を離す → Ctrl を離す
        with self.assertNoLogs(self.keyboard._logger, "ERROR"):
            self.keyboard.on_press(Key.ctrl_l)
            self.keyboard.on_press(char("", vk=70))
            self.keyboard.suspend()
            self.keyboard.on_release(char("", vk=70))
            self.keyboard.on_release(Key.ctrl_l)
        self.assertEqual(self.sent(), [])
        SwitchKeyboardController.resume()
        self.keyboard.on_press(char("f", vk=70))
        self.assertEqual(self.sent(), [("input", Button.B)])

    def test_ctrl_held_when_a_new_listener_starts_is_silent(self):
        # Ctrl を押したままウィンドウをクリックして、受け付けが作り直された場合(Ctrl を押したことを知らない)
        with self.assertNoLogs(self.keyboard._logger, "ERROR"):
            self.keyboard.on_press(char("", vk=70))
            self.keyboard.on_release(char("", vk=70))
            self.keyboard.on_release(Key.ctrl_l)
        self.assertEqual(self.sent(), [])

    def test_keys_released_while_suspended_do_not_stay_ignored(self):
        self.keyboard.on_press(Key.ctrl_l)
        self.keyboard.on_press(char("", vk=70))
        self.keyboard.suspend()
        self.keyboard.on_release(char("", vk=70))
        self.keyboard.on_release(Key.ctrl_l)
        SwitchKeyboardController.resume()
        self.assertEqual((self.keyboard._alt_keys, self.keyboard._ignored_keys), (set(), set()))


class MenuOpenTest(MenuKeyTestMixin, AltKeyTest):
    """メニューを操作している間(Alt + F で開いた後、Alt を離してから押す矢印キーなど)は、キーをゲーム機に送らない"""

    def setUp(self):
        super().setUp()
        self.useMenuState()
        self.keyboard.key_map = {"a": Button.A, "f": Button.B, Key.down: Direction.DOWN, Key.enter: Button.X}
        self.keyboard.key_map_D = {Key.down: Direction.DOWN}

    def test_arrow_keys_after_alt_f_are_not_sent(self):
        # Alt + F でメニューを開き、Alt も F も離してから、下の矢印キーを押す
        self.keyboard.on_press(Key.alt_l)
        self.keyboard.on_press(char("f", vk=70))
        self.menu_open = True
        self.keyboard.on_release(char("f", vk=70))
        self.keyboard.on_release(Key.alt_l)
        for _ in range(3):
            self.keyboard.on_press(Key.down)
            self.keyboard.on_release(Key.down)
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.keyboard.holdingDir, [])

    def test_the_key_that_closes_the_menu_is_ignored_until_it_is_released(self):
        # Enter で項目を選ぶと、メニューは閉じる。Enter を離すのは、その後
        self.menu_open = True
        self.keyboard.on_press(Key.enter)
        self.menu_open = False
        self.keyboard.on_press(Key.enter)
        self.keyboard.on_release(Key.enter)
        self.assertEqual(self.sent(), [])

    def test_keys_work_again_after_the_menu_is_closed(self):
        self.menu_open = True
        self.keyboard.on_press(Key.down)
        self.keyboard.on_release(Key.down)
        self.menu_open = False
        self.keyboard.on_press(Key.down)
        self.keyboard.on_release(Key.down)
        self.assertEqual(self.sent(), [("input", Direction.DOWN), ("inputEnd", Direction.DOWN)])
        self.assertEqual(self.keyboard._ignored_keys, set())

    def test_a_key_held_before_the_menu_opens_is_still_released(self):
        self.keyboard.on_press(char("a", vk=65))
        self.menu_open = True
        self.keyboard.on_release(char("a", vk=65))
        self.assertEqual(self.sent(), [("input", Button.A), ("inputEnd", Button.A)])

    def test_the_real_check_answers_without_a_menu(self):
        import Keyboard

        self.assertIs(Keyboard.menu_is_open(), False)


if __name__ == "__main__":
    unittest.main()
