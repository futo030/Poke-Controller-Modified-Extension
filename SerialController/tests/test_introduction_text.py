#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
機能紹介の文章(assets/introduction/introduction.md)のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constant  # noqa: E402
from services import introduction_store  # noqa: E402


class IntroductionTextTest(unittest.TestCase):
    def test_first_page_names_the_current_version(self):
        # バージョンを上げたら、機能紹介の最初のページの見出し(と中身)も、そのバージョンのものに書き換える
        pages = introduction_store.load_pages(introduction_store.TK)
        self.assertEqual(pages[0].title, f"ver.{Constant.VERSION}の新機能紹介")
        self.assertTrue(any(f"ver.{Constant.VERSION}" in text for _, text in pages[0].lines))

    def test_images_exist(self):
        for page in introduction_store.load_pages(introduction_store.TK):
            if page.image:
                with self.subTest(page=page.title):
                    self.assertTrue(os.path.isfile(os.path.join(introduction_store.INTRODUCTION_DIR, page.image)))

    def test_old_names_are_not_used(self):
        for kind in (introduction_store.TK, introduction_store.WEB):
            path = os.path.join(introduction_store.INTRODUCTION_DIR, introduction_store.KINDS[kind][0])
            with open(path, encoding="utf-8") as file:
                text = file.read()
            for old in ("Startup Guide", "Create a New Script", "新しくなった点の紹介"):
                self.assertNotIn(old, text)


if __name__ == "__main__":
    unittest.main()
