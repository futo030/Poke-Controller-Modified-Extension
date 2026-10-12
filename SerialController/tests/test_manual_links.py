#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instruction Manual の中のリンク(URL)と、「ハードウェアの設定」の項目のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Manual  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "static")
HARDWARE_LINKS = {
    "Arduino Leonardo": "https://pokecontroller.info/SetLeonardo",
    "CH552 Serial": "https://blog.bzl-web.com/entry/2022/11/24/001148",
}


class SplitLinksTest(unittest.TestCase):
    def test_urls_are_separated_from_the_text(self):
        url = HARDWARE_LINKS["CH552 Serial"]
        self.assertEqual(Manual.split_links(f"CH552 Serial: {url}"), [("CH552 Serial: ", None), (url, url)])
        self.assertEqual(Manual.split_links("文章だけ"), [("文章だけ", None)])
        self.assertEqual(Manual.split_links(""), [])

    def test_a_url_ends_before_brackets_spaces_and_japanese_text(self):
        self.assertEqual(
            Manual.split_links("アドレス(http://127.0.0.1:8765/ など)を開きます。"),
            [("アドレス(", None), ("http://127.0.0.1:8765/", "http://127.0.0.1:8765/"), (" など)を開きます。", None)],
        )
        self.assertEqual(Manual.split_links("(https://example.com/a)と")[1][0], "https://example.com/a")
        self.assertEqual(Manual.split_links("https://example.com/aを開く")[0][0], "https://example.com/a")

    def test_trailing_punctuation_is_not_part_of_the_url(self):
        parts = Manual.split_links("see https://example.com/a.b, then https://example.com/c.")
        self.assertEqual([url for _, url in parts if url], ["https://example.com/a.b", "https://example.com/c"])
        self.assertEqual("".join(text for text, _ in parts), "see https://example.com/a.b, then https://example.com/c.")

    def test_only_web_addresses_become_links(self):
        for text in ("file:///C:/Windows/notepad.exe", "javascript:alert(1)", "ftp://example.com/x", "C:\\Users\\name"):
            self.assertEqual(Manual.split_links(text), [(text, None)])


class HardwareTopicTest(unittest.TestCase):
    def check(self, topics):
        titles = [topic.title for topic in topics]
        self.assertIn("ハードウェアの設定", titles)
        # 機器の設定は、ツールの側の設定(最初の設定)より前に読む
        self.assertEqual(titles.index("ハードウェアの設定") + 1, titles.index("最初の設定"))
        lines = [text for kind, text in topics[titles.index("ハードウェアの設定")].lines if kind == "li"]
        for name, url in HARDWARE_LINKS.items():
            line = next(text for text in lines if text.startswith(name))
            self.assertEqual([link for _, link in Manual.split_links(line) if link], [url])

    def test_the_window_manual_has_the_topic(self):
        self.check(Manual.load_topics())

    def test_the_web_manual_has_the_topic(self):
        self.check(Manual._load_file("manual_web.md"))


class DiscordTopicTest(unittest.TestCase):
    def test_both_manuals_explain_the_discord_setup_with_the_images(self):
        for topics in (Manual.load_topics(), Manual._load_file("manual_web.md")):
            titles = [topic.title for topic in topics]
            topic = topics[titles.index("Discord 通知の設定")]
            images = [text for kind, text in topic.lines if kind == "img"]
            self.assertEqual(len(images), 5)
            for name in images:
                # Web ブラウザ版は、画像の名前に、フォルダーの区切りを使えない
                self.assertNotIn("/", name)
                self.assertTrue(os.path.isfile(os.path.join(Manual.MANUAL_DIR, name)), name)
            headings = [text for kind, text in topic.lines if kind == "h"]
            self.assertEqual([text[0] for text in headings], ["1", "2", "3", "4"])


class WebViewerTest(unittest.TestCase):
    def test_the_web_viewer_uses_the_same_rule_and_safe_links(self):
        with open(os.path.join(STATIC_DIR, "extras.js"), encoding="utf-8") as file:
            script = file.read()
        # Manual.py の URL_PATTERN と同じ文字の範囲
        self.assertIn(r"/https?:\/\/[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%]+/g", script)
        self.assertEqual(Manual.URL_PATTERN.pattern, r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%]+")
        self.assertIn('link.rel = "noopener noreferrer"', script)
        self.assertIn('link.target = "_blank"', script)
        # リンクの文字は、textContent で入れる(マニュアルの文章を HTML として解釈しない)
        self.assertNotIn("innerHTML = text", script)


if __name__ == "__main__":
    unittest.main()
