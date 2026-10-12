#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pyproject.toml(uv 用)と requirements.txt(uv を使わない環境用)が食い違っていないことのテスト

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import re
import sys
import tomllib
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constant  # noqa: E402

REPOSITORY_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_pyproject() -> dict:
    with open(os.path.join(REPOSITORY_DIR, "pyproject.toml"), "rb") as file:
        return tomllib.load(file)


def read_requirements(name: str) -> list:
    """requirements のファイルに書いてある行(コメントと空行を除く。空白は詰める)"""
    with open(os.path.join(REPOSITORY_DIR, name), encoding="utf-8") as file:
        lines = [line.split("#")[0].strip() for line in file]
    return [re.sub(r"\s+", "", line) for line in lines if line]


def normalized(requirements: list) -> list:
    return sorted(re.sub(r"\s+", "", requirement).lower() for requirement in requirements)


class PackagingTest(unittest.TestCase):
    def test_version_is_the_same_as_the_application(self):
        # バージョンを上げるときは、Constant.VERSION と pyproject.toml の両方を書き換える
        self.assertEqual(read_pyproject()["project"]["version"], Constant.VERSION)

    def test_dependencies_are_the_same_as_the_requirements_files(self):
        # uv の環境には、Web ブラウザ版のライブラリも初めから入れる
        dependencies = read_pyproject()["project"]["dependencies"]
        expected = read_requirements("requirements.txt") + read_requirements("requirements-web.txt")
        self.assertEqual(normalized(dependencies), normalized(expected))

    def test_python_version_file_names_a_minor_version(self):
        # 細かい版(3.13.16 など)まで書くと、その版を知らない uv では環境を作れない
        with open(os.path.join(REPOSITORY_DIR, ".python-version"), encoding="utf-8") as file:
            self.assertRegex(file.read().strip(), r"^3\.\d+$")


if __name__ == "__main__":
    unittest.main()
