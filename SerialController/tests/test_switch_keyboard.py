#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
画面上のキーボード(Keyboard ウィンドウ)の、キーの配置(services/switch_keyboard_layout.py)と
送信(services/keyboard_typer.py)のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import transport_scenarios  # noqa: E402
from Commands import SwitchKeyboard  # noqa: E402
from Commands.Keys import Button, KeyPress  # noqa: E402
from Commands.Sender import Sender  # noqa: E402
from Commands.SwitchKeyboard import KEY  # noqa: E402
from services import switch_keyboard_layout as layout  # noqa: E402
from services.keyboard_typer import MAX_PENDING, KeyboardTyper  # noqa: E402


def wait_until(condition, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return bool(condition())


class LayoutTest(unittest.TestCase):
    def test_every_page_is_5_rows_of_11_keys(self):
        for page in layout.PAGES:
            for small in (False, True):
                rows = layout.page_rows(page, small)
                self.assertEqual([len(row) for row in rows], [layout.COLUMNS] * layout.ROWS, (page, small))
                keys = [c for row in rows for c in row if c]
                self.assertEqual(len(keys), len(set(keys)), (page, small))
        with self.assertRaises(KeyError):
            layout.page_rows("none")

    def test_hiragana_page_matches_the_switch_keyboard(self):
        rows = layout.page_rows(layout.PAGE_HIRAGANA)
        self.assertEqual("".join(c or "_" for c in rows[0]), "「わらやまはなたさかあ")
        self.assertEqual("".join(c or "_" for c in rows[1]), "」をり_みひにちしきい")
        self.assertEqual("".join(c or "_" for c in rows[2]), "ーんるゆむふぬつすくう")
        self.assertEqual("".join(c or "_" for c in rows[3]), "?、れ_めへねてせけえ")
        self.assertEqual("".join(c or "_" for c in rows[4]), "!。ろよもほのとそこお")

    def test_katakana_page_is_the_same_layout_in_katakana(self):
        rows = layout.page_rows(layout.PAGE_KATAKANA)
        self.assertEqual("".join(c or "_" for c in rows[0]), "「ワラヤマハナタサカア")
        self.assertEqual("".join(c or "_" for c in rows[4]), "!。ロヨモホノトソコオ")
        small = layout.page_rows(layout.PAGE_KATAKANA, True)
        self.assertEqual("".join(c or "_" for c in small[0]), "___ッャァパバダザガ")
        self.assertEqual("".join(c or "_" for c in small[2]), "___ヴュゥプブヅズグ")

    def test_alphabet_and_symbol_pages(self):
        lower, upper = layout.page_rows(layout.PAGE_LOWER), layout.page_rows(layout.PAGE_UPPER)
        self.assertEqual("".join(c for row in lower for c in row), "abcdefghijklmnopqrstuvwxyz")
        self.assertEqual("".join(c for row in upper for c in row), "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        self.assertEqual("".join(lower[0]), "abcdefghijk")
        symbol = layout.page_rows(layout.PAGE_SYMBOL)
        self.assertEqual("".join(symbol[0]), "1234567890-")
        self.assertEqual("".join(symbol[1]), "!@#$%^&*()_")
        self.assertEqual("".join(symbol[3][:10]), "<>;:\"',.?/")
        # 小字のページは、かな・カナだけ(ほかのページでは、同じ配置のまま)
        self.assertEqual(layout.page_rows(layout.PAGE_LOWER, True), lower)

    def test_typed_text(self):
        cases = {"a": "a", "Z": "Z", "1": "1", "@": "@", " ": " ", "あ": "a", "し": "si", "ち": "ti", "つ": "tu", "ふ": "hu",
                 "ん": "nn", "を": "wo", "が": "ga", "じ": "zi", "ぢ": "di", "づ": "du", "ぱ": "pa", "ぁ": "xa", "ゃ": "xya",
                 "っ": "xtu", "ゎ": "xwa", "ゔ": "vu", "カ": "ka", "ヴ": "vu", "ッ": "xtu", "ー": "-", "「": "[", "」": "]",
                 "、": ",", "。": ".", "Ａ": "A", "１": "1", "！": "!","　": " "}
        for character, expected in cases.items():
            self.assertEqual(layout.typed_text(character), expected, character)
        for character in ("※", "々", "漢", "¥", "ヵ", "", "ab", "\n"):
            self.assertIsNone(layout.typed_text(character), character)
            self.assertFalse(layout.sendable(character))

    def test_everything_sent_is_half_width(self):
        # どのページのどのキーも、送る文字は、マイコンが打てる半角の文字だけ
        for page in layout.PAGES:
            for small in (False, True):
                for row in layout.page_rows(page, small):
                    for character in row:
                        typed = layout.typed_text(character) if character else None
                        if typed is not None:
                            self.assertEqual(SwitchKeyboard.find_invalid_characters(typed), [], character)
        # かな・カナと、英数字のページのキーは、すべて送れる
        for page in (layout.PAGE_HIRAGANA, layout.PAGE_KATAKANA, layout.PAGE_LOWER, layout.PAGE_UPPER):
            for small in (False, True):
                for row in layout.page_rows(page, small):
                    for character in row:
                        self.assertTrue(not character or layout.sendable(character), character)

    def test_convert_text(self):
        self.assertEqual(layout.convert_text("ねこ"), ("neko", []))
        self.assertEqual(layout.convert_text("きゃっと"), ("kixyaxtuto", []))
        self.assertEqual(layout.convert_text("ポケモン"), ("pokemonn", []))
        self.assertEqual(layout.convert_text("abc 123!"), ("abc 123!", []))
        self.assertEqual(layout.convert_text("AB12"), ("AB12", []))
        self.assertEqual(layout.convert_text("らーめん、「あ」。"), ("ra-menn,[a].", []))
        self.assertEqual(layout.convert_text("漢字とかな※漢"), ("tokana", ["漢", "字", "※"]))
        self.assertEqual(layout.convert_text(""), ("", []))
        self.assertTrue(layout.has_kana("aあ"))
        self.assertFalse(layout.has_kana("abc"))

    def test_mode_keys_reach_the_target_from_any_mode(self):
        # 実機で確かめた、キーを 1 回押したときのモードの移り方で、キーの並びをたどる
        after = {
            (layout.MODE_KANA, layout.KEY_HIRAGANA): layout.MODE_KATAKANA,
            (layout.MODE_KATAKANA, layout.KEY_HIRAGANA): layout.MODE_KANA,
            (layout.MODE_ALNUM, layout.KEY_HIRAGANA): layout.MODE_KANA,
            (layout.MODE_KANA, layout.KEY_HANZEN): layout.MODE_ALNUM,
            (layout.MODE_KATAKANA, layout.KEY_HANZEN): layout.MODE_ALNUM,
            (layout.MODE_ALNUM, layout.KEY_HANZEN): layout.MODE_KANA,
        }
        modes = (layout.MODE_KANA, layout.MODE_KATAKANA, layout.MODE_ALNUM)
        for target in modes:
            for start in modes:
                # 今のモードが分からないとき: どのモードから始めても、目的のモードになる
                mode = start
                for key in layout.mode_keys(None, target):
                    mode = after[(mode, key)]
                self.assertEqual(mode, target, (start, target))
                # 今のモードが分かっているとき: 2 回以内で、目的のモードになる
                keys = layout.mode_keys(start, target)
                self.assertLessEqual(len(keys), 2)
                mode = start
                for key in keys:
                    mode = after[(mode, key)]
                self.assertEqual(mode, target, (start, target))
            self.assertEqual(layout.mode_keys(target, target), ())
        self.assertEqual(set(layout.PAGE_MODES), set(layout.PAGES))

    def test_character_mode_and_segments(self):
        self.assertEqual(layout.character_mode("あ"), layout.MODE_KANA)
        self.assertEqual(layout.character_mode("ア"), layout.MODE_KATAKANA)
        for character in ("a", "1", "!", " ", "\uff21", "\u3000"):
            self.assertEqual(layout.character_mode(character), layout.MODE_ALNUM, character)
        # 「 」 、 。 ー ・ 〜 は、かな・カナのどちらでも打てる(今がそのどちらかなら、切り替えない)
        self.assertEqual(layout.character_mode("ー"), layout.MODE_KANA)
        self.assertEqual(layout.character_mode("ー", layout.MODE_KATAKANA), layout.MODE_KATAKANA)
        self.assertEqual(layout.character_mode("・", layout.MODE_ALNUM), layout.MODE_KANA)
        self.assertIsNone(layout.character_mode("漢"))
        self.assertEqual(layout.segment_text("ポケモンGet! がっ「あ」ー 1"), (
            [(layout.MODE_KATAKANA, "pokemonn"), (layout.MODE_ALNUM, "Get! "), (layout.MODE_KANA, "gaxtu[a]-"),
             (layout.MODE_ALNUM, " 1")], []))
        self.assertEqual(layout.segment_text("ラーメン"), ([(layout.MODE_KATAKANA, "ra-menn")], []))
        self.assertEqual(layout.segment_text("漢a字"), ([(layout.MODE_ALNUM, "a")], ["漢", "字"]))
        self.assertEqual(layout.segment_text(""), ([], []))

    def test_kana_conversion_helpers(self):
        self.assertEqual(layout.to_katakana("あいうabcっ"), "アイウabcッ")
        self.assertEqual(layout.to_hiragana("アイウabcッヴ"), "あいうabcっゔ")


class TyperTest(unittest.TestCase):
    """送信(送る先は、代役のポート)"""

    def setUp(self):
        self.original_format = KeyPress.serial_data_format_name
        self.addCleanup(lambda: setattr(KeyPress, "serial_data_format_name", self.original_format))
        KeyPress.serial_data_format_name = "Default"
        self.sender = Sender(lambda: False)
        self.log = []
        self.port = transport_scenarios.FakeSerial(self.log)
        self.sender.ser = self.port
        self.messages = []
        self.sleeps = []
        self.typer = KeyboardTyper(self.sender, on_message=lambda text, error: self.messages.append((text, error)),
                                   sleep=self.sleeps.append)
        self.addCleanup(self.typer.close)

    def rows(self) -> list:
        # 代役のポートは、行を "text 行" の形で記録する
        return [str(row)[5:] if str(row).startswith("text ") else str(row) for row in self.log]

    def test_text_is_sent_as_quoted_rows_in_order(self):
        self.assertTrue(self.typer.type_text("neko", "ねこ (neko)"))
        self.assertTrue(self.typer.type_key(KEY.ENTER))
        self.assertTrue(wait_until(lambda: len(self.messages) == 2))
        self.assertEqual(self.rows(), ['"neko"', "Key 40"])
        self.assertEqual(self.messages, [("送信: ねこ (neko)", False), ("送信: ENTER", False)])
        # マイコンが打ち終わるまで待つ(スクリプトの TypeString / TypeKey と同じ時間)
        self.assertEqual(self.sleeps, [SwitchKeyboard.text_seconds("neko"), SwitchKeyboard.key_seconds("Key")])

    def test_same_rows_as_the_script_functions(self):
        # スクリプトの KeyBoard_Init の行("end")は、送らない(入力を離してしまうため)
        self.typer.type_text("abcdefghijklmnopq")
        self.assertTrue(wait_until(lambda: len(self.messages) == 1))
        self.assertEqual(self.rows(), ['"abcdefghijklm"', '"nopq"'])
        self.assertNotIn("end", self.rows())

    def test_invalid_text_is_not_sent(self):
        self.assertFalse(self.typer.type_text("あ"))
        self.assertFalse(self.typer.type_text(""))
        time.sleep(0.05)
        self.assertEqual(self.rows(), [])

    def test_ok_presses_the_plus_button(self):
        self.assertTrue(self.typer.press_button())
        self.assertTrue(wait_until(lambda: len(self.messages) == 1))
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        # + ボタンを押した行(Default の形式での + は 0x0800)と、離した行
        self.assertEqual(int(rows[0].split()[0], 16) & 0x0800, 0x0800)
        self.assertEqual(rows[1], "0x0000 8")
        self.assertEqual(Button.PLUS.name, "PLUS")
        self.assertEqual(self.messages, [("送信: OK (+)", False)])

    def test_nx_format_sends_keyboard_packets(self):
        KeyPress.serial_data_format_name = "NX"
        self.assertEqual(self.typer.unavailable_reason(), "")
        self.typer.type_text("a")
        self.assertTrue(wait_until(lambda: len(self.messages) == 1))
        self.assertEqual(self.messages, [("送信: a", False)])
        self.assertTrue(self.log)

    def test_unsupported_format_and_closed_port(self):
        KeyPress.serial_data_format_name = "Qingpi"
        self.assertIn("Data Format が Default / NX の場合のみ", self.typer.unavailable_reason())
        self.assertFalse(self.typer.type_text("a"))
        self.assertFalse(self.typer.press_button())
        self.assertEqual(self.messages[-1][1], True)
        KeyPress.serial_data_format_name = "Default"
        self.sender.ser = None
        self.assertIn("接続していません", self.typer.unavailable_reason())
        self.assertFalse(self.typer.type_key(KEY.SPACE))
        time.sleep(0.05)
        self.assertEqual(self.rows(), [])

    def test_mode_is_switched_only_when_needed(self):
        # 初めは、今のモードが分からないので、どのモードからでも合う並びを送る。その後は、覚えているモードからの最短
        self.typer.type_text("ka", mode=layout.MODE_KANA)
        self.typer.type_text("ki", mode=layout.MODE_KANA)
        self.typer.type_text("a", mode=layout.MODE_ALNUM)
        self.typer.type_text("ka", mode=layout.MODE_KATAKANA)
        self.typer.type_text("x")
        self.assertTrue(wait_until(lambda: len(self.messages) == 5))
        self.assertEqual(self.rows(), ["Key 136", "Key 53", "Key 53", '"ka"', '"ki"', "Key 53", '"a"', "Key 53", "Key 136", '"ka"',
                                       '"x"'])
        self.assertEqual(self.typer.mode, layout.MODE_KATAKANA)

    def test_set_mode_forget_mode_and_direct_keys(self):
        self.typer.set_mode(layout.MODE_ALNUM)
        self.typer.set_mode(layout.MODE_ALNUM)
        self.assertTrue(wait_until(lambda: len(self.messages) == 2))
        self.assertEqual(self.rows(), ["Key 136", "Key 53"])
        self.assertEqual(self.messages[0], ("送信: 入力モード: 英字", False))
        # モードを切り替えるキーをじかに送ったときは、その先のモードを覚える(英字 → 半角/全角 → かな)
        self.typer.type_key(KEY.JP_HANZEN)
        self.typer.set_mode(layout.MODE_KATAKANA)
        self.assertTrue(wait_until(lambda: len(self.messages) == 4))
        self.assertEqual(self.rows()[2:], ["Key 53", "Key 136"])
        # 忘れた後は、初めから合わせる
        self.typer.forget_mode()
        self.typer.set_mode(layout.MODE_KATAKANA)
        self.assertTrue(wait_until(lambda: len(self.messages) == 5))
        self.assertEqual(self.rows()[4:], ["Key 136", "Key 53", "Key 53", "Key 136"])

    def test_segments_are_typed_with_mode_switches(self):
        segments, _ = layout.segment_text("ポケモンGet! ねこ")
        self.assertTrue(self.typer.type_segments(segments, "ポケモンGet! ねこ"))
        self.assertTrue(wait_until(lambda: len(self.messages) == 1))
        self.assertEqual(self.rows(), ["Key 136", "Key 53", "Key 53", "Key 136", '"pokemonn"', "Key 53", '"Get! "', "Key 53",
                                       '"neko"'])
        self.assertEqual(self.messages, [("送信: ポケモンGet! ねこ", False)])
        self.assertFalse(self.typer.type_segments([], ""))
        self.assertFalse(self.typer.type_segments([(layout.MODE_KANA, "あ")], "あ"))

    def test_too_many_pending_requests_are_refused(self):
        import threading

        gate = threading.Event()
        typer = KeyboardTyper(self.sender, on_message=lambda text, error: self.messages.append((text, error)),
                              sleep=lambda seconds: gate.wait(5))
        self.addCleanup(typer.close)
        accepted = sum(typer.type_text("a") for _ in range(MAX_PENDING + 20))
        self.assertLessEqual(accepted, MAX_PENDING + 1)
        self.assertGreaterEqual(accepted, MAX_PENDING)
        self.assertIn("送信待ちが多すぎます", self.messages[-1][0])
        gate.set()

    def test_close_stops_sending(self):
        self.typer.close()
        self.assertFalse(self.typer.type_text("a"))
        time.sleep(0.05)
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
