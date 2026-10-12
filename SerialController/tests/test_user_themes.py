#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
利用者が足すテーマ(themes フォルダーの *.json)の読み込みのテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Theme  # noqa: E402


def colors(**changes):
    values = dict(Theme.THEMES["dark_gray"]["colors"])
    result = {role: values[role] for role in Theme.USER_THEME_ROLES}
    result.update(changes)
    return result


class ParseTest(unittest.TestCase):
    def test_valid_theme(self):
        theme = Theme.parse_user_theme({"name": " 夜 ", "dark": True, "colors": colors(bg="#101010", fg="#EEEEEE")})
        self.assertEqual((theme["name"], theme["dark"]), ("夜", True))
        self.assertEqual(theme["colors"]["bg"], "#101010")
        # 色は小文字にそろえる。書いていない役割は、ほかの役割の色から決める
        self.assertEqual(theme["colors"]["fg"], "#eeeeee")
        self.assertEqual((theme["colors"]["text_fg"], theme["colors"]["menu_fg"]), ("#eeeeee", "#eeeeee"))
        self.assertEqual(theme["colors"]["menu"], theme["colors"]["surface"])
        # 元からあるテーマと同じ役割を、すべて持つ
        self.assertEqual(set(theme["colors"]), set(Theme.THEMES["dark_gray"]["colors"]))

    def test_optional_roles_can_be_written(self):
        theme = Theme.parse_user_theme({"name": "a", "colors": colors(text_fg="#112233", menu="#445566")})
        self.assertEqual((theme["colors"]["text_fg"], theme["colors"]["menu"]), ("#112233", "#445566"))

    def test_dark_is_guessed_from_the_background(self):
        self.assertIs(Theme.parse_user_theme({"name": "a", "colors": colors(bg="#202020")})["dark"], True)
        self.assertIs(Theme.parse_user_theme({"name": "a", "colors": colors(bg="#f0f0f0")})["dark"], False)

    def test_invalid_themes_tell_the_reason(self):
        cases = [
            ([], "{ }"),
            ({"colors": colors()}, "name"),
            ({"name": "  ", "colors": colors()}, "name"),
            ({"name": "x" * 41, "colors": colors()}, "40"),
            ({"name": "a"}, "colors"),
            ({"name": "a", "colors": {k: v for k, v in colors().items() if k != "sash"}}, "sash"),
            ({"name": "a", "colors": colors(bgg="#000000")}, "bgg"),
            ({"name": "a", "colors": colors(link="red")}, "link"),
            ({"name": "a", "colors": colors(link="#fff")}, "link"),
            ({"name": "a", "colors": colors(link=123)}, "link"),
            ({"name": "a", "dark": "yes", "colors": colors()}, "dark"),
        ]
        for data, word in cases:
            with self.subTest(word=word):
                with self.assertRaises(ValueError) as caught:
                    Theme.parse_user_theme(data)
                self.assertIn(word, str(caught.exception))


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))
        self.addCleanup(lambda: [Theme.THEMES.pop(theme_id) for theme_id in Theme.user_theme_ids()])
        self.built_in = Theme.theme_ids()

    def write(self, name, data):
        with open(os.path.join(self.directory, name), "w", encoding="utf-8") as file:
            file.write(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))

    def test_missing_folder_is_not_an_error(self):
        self.assertEqual(Theme.load_user_themes(os.path.join(self.directory, "none")), [])
        self.assertEqual(Theme.theme_ids(), self.built_in)

    def test_themes_are_added_after_the_built_in_ones(self):
        self.write("night.json", {"name": "夜", "colors": colors()})
        self.write("b.JSON", {"name": "B", "dark": False, "colors": colors()})
        self.write("note.txt", "not a theme")
        self.assertEqual(Theme.load_user_themes(self.directory), [])
        self.assertEqual(Theme.theme_ids(), self.built_in + ["user_b", "user_night"])
        self.assertEqual(Theme.user_theme_ids(), ["user_b", "user_night"])
        self.assertEqual(Theme.theme_name("user_night"), "夜")

    def test_broken_files_are_skipped_with_reasons(self):
        self.write("good.json", {"name": "Good", "colors": colors()})
        self.write("broken.json", '{"name": "x",')
        self.write("bad.json", {"name": "Bad", "colors": colors(bg="blue")})
        problems = dict(Theme.load_user_themes(self.directory))
        self.assertEqual(Theme.user_theme_ids(), ["user_good"])
        self.assertEqual(set(problems), {"broken.json", "bad.json"})
        self.assertIn("JSON", problems["broken.json"])
        self.assertIn("bg", problems["bad.json"])

    def test_reloading_replaces_the_previous_user_themes(self):
        self.write("a.json", {"name": "A", "colors": colors()})
        Theme.load_user_themes(self.directory)
        os.remove(os.path.join(self.directory, "a.json"))
        self.write("c.json", {"name": "C", "colors": colors(bg="#123456")})
        Theme.load_user_themes(self.directory)
        self.assertEqual(Theme.user_theme_ids(), ["user_c"])
        self.assertEqual(Theme.THEMES["user_c"]["colors"]["bg"], "#123456")

    def test_file_with_bom_is_read(self):
        with open(os.path.join(self.directory, "bom.json"), "w", encoding="utf-8-sig") as file:
            json.dump({"name": "BOM", "colors": colors()}, file)
        self.assertEqual(Theme.load_user_themes(self.directory), [])
        self.assertEqual(Theme.user_theme_ids(), ["user_bom"])

    def test_template_can_be_loaded_as_it_is(self):
        first = Theme.create_user_theme(self.directory, "dark_blue")
        second = Theme.create_user_theme(self.directory, "default")
        self.assertEqual([os.path.basename(first), os.path.basename(second)], ["my_theme.json", "my_theme_2.json"])
        self.assertEqual(Theme.load_user_themes(self.directory), [])
        self.assertEqual(Theme.user_theme_ids(), ["user_my_theme", "user_my_theme_2"])
        # 元にしたテーマと同じ色。デフォルトのテーマは、色が決まっていないので、白基調の色を入れる
        self.assertEqual(Theme.THEMES["user_my_theme"]["colors"], Theme.THEMES["dark_blue"]["colors"])
        self.assertIs(Theme.THEMES["user_my_theme"]["dark"], True)
        self.assertEqual(Theme.THEMES["user_my_theme_2"]["colors"], Theme.THEMES["light_white"]["colors"])
        self.assertEqual(Theme.theme_name("user_my_theme_2"), "My Theme 2")

    def test_existing_file_is_not_overwritten(self):
        self.write("my_theme.json", "mine")
        path = Theme.create_user_theme(self.directory, "dark_gray")
        self.assertEqual(os.path.basename(path), "my_theme_2.json")
        with open(os.path.join(self.directory, "my_theme.json"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "mine")

    def test_save_writes_a_new_file_and_registers_the_theme(self):
        data = {"name": "夜の色", "dark": True, "colors": colors(bg="#101010")}
        stem = Theme.save_user_theme(data, None, self.directory)
        self.assertEqual(stem, "my_theme")
        self.assertEqual(Theme.THEMES["user_my_theme"]["colors"]["bg"], "#101010")
        self.assertEqual(Theme.save_user_theme(dict(data, name="2 つ目"), None, self.directory), "my_theme_2")
        with open(os.path.join(self.directory, "my_theme.json"), encoding="utf-8") as file:
            saved = json.load(file)
        self.assertEqual((saved["name"], saved["dark"], list(saved["colors"])), ("夜の色", True, list(Theme.USER_THEME_ROLES)))
        # 保存したファイルは、そのまま読み込める
        self.assertEqual(Theme.load_user_themes(self.directory), [])
        self.assertEqual(Theme.user_theme_ids(), ["user_my_theme", "user_my_theme_2"])
        self.assertEqual([name for name in os.listdir(self.directory) if name.endswith(".tmp")], [])

    def test_save_overwrites_the_given_file(self):
        stem = Theme.save_user_theme({"name": "A", "dark": False, "colors": colors()}, None, self.directory)
        again = Theme.save_user_theme({"name": "A 改", "dark": False, "colors": colors(fg="#123456")}, stem, self.directory)
        self.assertEqual(again, stem)
        self.assertEqual(os.listdir(self.directory), ["my_theme.json"])
        self.assertEqual((Theme.theme_name("user_my_theme"), Theme.THEMES["user_my_theme"]["colors"]["fg"]), ("A 改", "#123456"))

    def test_invalid_theme_is_not_saved(self):
        with self.assertRaises(ValueError):
            Theme.save_user_theme({"name": "", "dark": False, "colors": colors()}, None, self.directory)
        with self.assertRaises(ValueError):
            Theme.save_user_theme({"name": "a", "dark": False, "colors": colors(bg="blue")}, None, self.directory)
        self.assertEqual(os.listdir(self.directory), [])

    def test_delete_removes_the_file_and_the_theme(self):
        stem = Theme.save_user_theme({"name": "A", "dark": False, "colors": colors()}, None, self.directory)
        Theme.delete_user_theme(stem, self.directory)
        self.assertEqual((os.listdir(self.directory), Theme.user_theme_ids()), ([], []))
        with self.assertRaises(OSError):
            Theme.delete_user_theme(stem, self.directory)

    def test_preview_theme_is_never_listed_or_saved(self):
        saved = dict(Theme._state)
        self.addCleanup(lambda: (Theme._state.update(saved), Theme.THEMES.pop(Theme.PREVIEW_THEME, None)))
        Theme.THEMES[Theme.PREVIEW_THEME] = Theme.parse_user_theme({"name": "p", "colors": colors()})
        Theme._state.update(theme=Theme.PREVIEW_THEME, preview_origin="dark_blue")
        self.assertNotIn(Theme.PREVIEW_THEME, Theme.theme_ids())
        self.assertNotIn(Theme.PREVIEW_THEME, Theme.user_theme_ids())
        self.assertEqual((Theme.current(), Theme.saved_theme_id()), (Theme.PREVIEW_THEME, "dark_blue"))
        Theme._state.update(theme="lavender", preview_origin=None)
        self.assertEqual(Theme.saved_theme_id(), "lavender")

    def test_is_color(self):
        self.assertTrue(all(Theme.is_color(value) for value in ("#000000", "#AbCdEf")))
        self.assertFalse(any(Theme.is_color(value) for value in ("#fff", "red", "", None, 0, "#12345g", "#1234567")))

    def test_unknown_theme_falls_back_to_default_without_a_window(self):
        self.write("a.json", {"name": "A", "colors": colors()})
        Theme.load_user_themes(self.directory)
        saved_theme, saved_root = Theme._state["theme"], Theme._state["root"]
        self.addCleanup(lambda: Theme._state.update(theme=saved_theme, root=saved_root))
        Theme._state.update(theme="user_a", root=None)
        os.remove(os.path.join(self.directory, "a.json"))
        Theme.reload_user_themes(self.directory)
        self.assertEqual(Theme.current(), Theme.DEFAULT_THEME)


if __name__ == "__main__":
    unittest.main()
