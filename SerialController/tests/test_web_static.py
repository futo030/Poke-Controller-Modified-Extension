#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web ブラウザ版の画面のファイル(web/static)の、書き間違いの検査

ブラウザを使わずにできる範囲の検査を行う:
- スクリプト(.js): 文字列の途中で行が切れていないこと、かっこの対応が取れていること
  (文字列の途中で行が切れると、スクリプト全体が動かなくなり、画面に何も表示されなくなる)
- ページ(index.html): スクリプトが使う id の部品があること、id が重複していないこと

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import glob
import io
import os
import re
import sys
import unittest

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(SERIAL_CONTROLLER_DIR, "web", "static")
sys.path.insert(0, SERIAL_CONTROLLER_DIR)

# この文字の後の「/」は、割り算ではなく正規表現の始まりとみなす
REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^\n")
PAIRS = {")": "(", "]": "[", "}": "{"}


def check_script(source: str) -> list:
    """
    スクリプトを先頭から読み、見つけた問題を「行番号: 内容」のリストで返す(問題が無ければ空)
    """
    problems = []
    stack = []  # 開いているかっこ: (文字, 行番号)。テンプレート文字列の中の ${ は "${"
    templates = []  # 開いているテンプレート文字列の、開始時点の stack の深さ
    line = 1
    i = 0
    last = "\n"  # 直前の、空白でない文字
    n = len(source)
    while i < n:
        c = source[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        two = source[i:i + 2]
        if two == "//":
            end = source.find("\n", i)
            i = n if end < 0 else end
            continue
        if two == "/*":
            end = source.find("*/", i + 2)
            if end < 0:
                problems.append(f"{line}: 閉じていないコメント")
                break
            line += source.count("\n", i, end)
            i = end + 2
            continue
        if c in "\"'":
            start = line
            i += 1
            while i < n and source[i] != c:
                if source[i] == "\\":
                    i += 1
                elif source[i] == "\n":
                    problems.append(f"{start}: 文字列の途中で行が切れている")
                    line += 1
                    break
                i += 1
            i += 1
            last = c
            continue
        if c == "`" or (c == "}" and templates and len(stack) == templates[-1]):
            # テンプレート文字列の始まり、または ${...} の終わり(文字列の続き)
            start = line
            if c == "`":
                templates.append(None)
            i += 1
            while i < n:
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == "\n":
                    line += 1
                if source[i] == "`":
                    templates.pop()
                    break
                if source[i:i + 2] == "${":
                    templates[-1] = len(stack)
                    i += 1
                    break
                i += 1
            else:
                problems.append(f"{start}: 閉じていないテンプレート文字列")
            i += 1
            last = "`"
            continue
        if c == "/" and last in REGEX_BEFORE:
            start = line
            i += 1
            in_class = False
            while i < n and (source[i] != "/" or in_class):
                if source[i] == "\\":
                    i += 1
                elif source[i] == "[":
                    in_class = True
                elif source[i] == "]":
                    in_class = False
                elif source[i] == "\n":
                    problems.append(f"{start}: 正規表現の途中で行が切れている")
                    line += 1
                    break
                i += 1
            i += 1
            last = "/"
            continue
        if c in "([{":
            stack.append((c, line))
        elif c in ")]}":
            if not stack or stack[-1][0] != PAIRS[c]:
                problems.append(f"{line}: 対応しない「{c}」")
            else:
                stack.pop()
        last = c
        i += 1
    problems += [f"{opened}: 閉じていない「{char}」" for char, opened in stack]
    if templates:
        problems.append("閉じていないテンプレート文字列")
    return problems


def read(name: str) -> str:
    with io.open(os.path.join(STATIC_DIR, name), encoding="utf-8") as file:
        return file.read()


class ScriptCheckerTest(unittest.TestCase):
    """検査そのものが、問題を見つけられること"""

    def test_good_scripts_pass(self):
        source = (
            'const a = "x\\n\\"y"; // comment "\n'
            "/* ' */ const b = `t ${a.map((v) => `${v}}`)} \n u`;\n"
            'const c = text.replace(/["\'`/]\\/[)]/g, (m) => ({ k: [1, 2] }));\n'
            "const d = a / 2 / 3;\n"
        )
        self.assertEqual(check_script(source), [])

    def test_broken_scripts_are_reported(self):
        # 文字列の途中で行が切れている(残りの部分も、閉じていない文字列として見つかる)
        problems = check_script('const a = "x' + chr(10) + 'y";' + chr(10))
        self.assertEqual(problems[0], "1: 文字列の途中で行が切れている")
        for source in ("function f() { return [1, 2;" + chr(10) + "}", "function f() { return (1;", "const a = `x ${b;", "if (a) { b(); ]"):
            self.assertTrue(check_script(source), source)


class DocumentsTest(unittest.TestCase):
    """Web 版のマニュアルと機能紹介(ウィンドウの画面のものとは別のファイル)"""

    def read(self, *names):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with io.open(os.path.join(root, "assets", *names), encoding="utf-8-sig") as file:
            return file.read()

    def titles(self, text):
        return [line[2:].strip() for line in text.splitlines() if line.startswith("# ")]

    def test_web_documents_are_used(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with io.open(os.path.join(root, "web", "static", "extras.js"), encoding="utf-8") as file:
            source = file.read()
        self.assertIn("/assets/manual/manual_web.md", source)
        self.assertIn("/assets/manual/scripting.md", source)
        self.assertIn("/assets/introduction/introduction_web.md", source)
        self.assertNotIn("/assets/introduction/introduction.md", source)

    def test_web_manual_and_common_topics(self):
        web = self.titles(self.read("manual", "manual_web.md"))
        common = self.titles(self.read("manual", "scripting.md"))
        window = self.titles(self.read("manual", "manual.md"))
        # スクリプトの説明は scripting.md だけに書く(ウィンドウの画面・Web 版の両方が、このファイルを表示する)
        self.assertFalse([title for title in window if title.startswith("スクリプト") or title == "Mcu コマンド"])
        self.assertIn("困ったとき", window)
        self.assertEqual(len(web), len(set(web)))
        # extras.js が、この項目の前に、スクリプトの書き方の項目を差し込む
        self.assertIn("Web 版で使えないもの", web)
        self.assertTrue([title for title in common if title.startswith("スクリプト")])
        self.assertIn("Mcu コマンド", common)
        self.assertFalse([title for title in web if title.startswith("スクリプト") or title == "Mcu コマンド"])
        # 起動のしかたは、どちらのマニュアルにも書く
        for text in (self.read("manual", "manual_web.md"), self.read("manual", "manual.md")):
            self.assertIn("python Window.py --ui web", text)
            self.assertIn("requirements-web.txt", text)

    def test_web_introduction_has_pages(self):
        titles = self.titles(self.read("introduction", "introduction_web.md"))
        self.assertGreater(len(titles), 3)
        self.assertEqual(len(titles), len(set(titles)))


class StaticFilesTest(unittest.TestCase):
    def test_scripts_have_no_broken_strings_or_brackets(self):
        scripts = sorted(glob.glob(os.path.join(STATIC_DIR, "*.js")))
        self.assertTrue(scripts)
        for path in scripts:
            with io.open(path, encoding="utf-8") as file:
                self.assertEqual(check_script(file.read()), [], os.path.basename(path))

    def test_page_loads_every_script(self):
        page = read("index.html")
        loaded = re.findall(r'<script src="/static/([^"]+)"', page)
        self.assertEqual(sorted(loaded), sorted(os.path.basename(p) for p in glob.glob(os.path.join(STATIC_DIR, "*.js"))))
        # app.js がほかのスクリプトより先(ほかのスクリプトは、app.js の関数を使う)
        self.assertEqual(loaded[0], "app.js")

    def test_ids_are_unique_and_used_ids_exist(self):
        page = read("index.html")
        ids = re.findall(r'\bid="([^"]+)"', page)
        duplicates = sorted({name for name in ids if ids.count(name) > 1})
        self.assertEqual(duplicates, [])
        # スクリプトが $("...") / byId("...") / getElementById("...") で使う id が、ページにあること
        # (スクリプトが自分で作る部品の id は除く)
        created = {"question-status", "question-program", "question-developer", "question-question", "question-tried"}
        missing = []
        for path in sorted(glob.glob(os.path.join(STATIC_DIR, "*.js"))):
            with io.open(path, encoding="utf-8") as file:
                source = file.read()
            for name in re.findall(r'(?:\$|byId|getElementById)\("([A-Za-z0-9_-]+)"\)', source):
                if name not in ids and name not in created:
                    missing.append(f"{os.path.basename(path)}: {name}")
        self.assertEqual(sorted(set(missing)), [])


if __name__ == "__main__":
    unittest.main()
