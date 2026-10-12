#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スクリプトから使う関数・クラスの、名前と引数が変わっていないことのテスト。

記録(tests/data/public_api.json)と比べる。関数や、省略できる引数を足したときは、
`python tests/public_api.py --write` で記録を作り直す。

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import public_api  # noqa: E402


class RecordTest(unittest.TestCase):
    """今のコードが、記録と変わらないこと"""

    @classmethod
    def setUpClass(cls):
        cls.current = public_api.collect()
        cls.recorded = public_api.load()

    def test_recorded_names_and_arguments_are_kept(self):
        self.assertIsNotNone(self.recorded, "記録がありません: python tests/public_api.py --write")
        broken, _ = public_api.compare(self.recorded, self.current)
        self.assertEqual(broken, [], "これまでのスクリプトが動かなくなる変更です")

    def test_every_public_name_is_recorded(self):
        self.assertIsNotNone(self.recorded, "記録がありません: python tests/public_api.py --write")
        _, unrecorded = public_api.compare(self.recorded, self.current)
        self.assertEqual(unrecorded, [], "記録を作り直してください: python tests/public_api.py --write")

    def test_collected_contents(self):
        files = self.current["files"]
        base = files["Commands/PythonCommandBase.py"]["classes"]
        # デコレータを付けた関数も、書いてあるとおりの引数になる
        self.assertEqual(base["PythonCommand"]["methods"]["press"], ["self", "buttons", "duration=0.1", "wait=0.1"])
        self.assertEqual(base["ImageProcPythonCommand"]["bases"], ["PythonCommand"])
        self.assertIn("isContainTemplate", base["ImageProcPythonCommand"]["methods"])
        self.assertIn("keys", base["PythonCommand"]["attributes"])
        self.assertNotIn("_sleep", base["PythonCommand"]["methods"])
        self.assertIn("print_t1", files["Commands/CommandBase.py"]["classes"]["Command"]["methods"])
        # クラスの外で足している属性と、その値
        self.assertIn("R_UP", files["Commands/Keys.py"]["classes"]["Direction"]["attributes"])
        self.assertNotIn("Direction", files["Commands/Keys.py"]["variables"])
        self.assertIn("NEUTRAL", files["Commands/Keys.py"]["variables"])
        values = self.current["values"]
        self.assertEqual(values["Commands.Keys.Direction"]["UP"], ["LEFT", 128, 255])
        self.assertEqual(values["Commands.Keys.Button"]["A"], 4)
        self.assertEqual(values["Commands.Keys.Button"]["START"], values["Commands.Keys.Button"]["PLUS"])
        self.assertEqual(values["Commands.Keys.Hat"]["TOP"], 0)
        # 一部の名前だけを対象にしたファイル
        self.assertEqual(list(files["Commands/SwitchKeyboard.py"]["classes"]), ["KEY"])
        self.assertEqual(files["Commands/SwitchKeyboard.py"]["functions"], {})


class CompareTest(unittest.TestCase):
    """記録との比べ方"""

    @staticmethod
    def api(parameters=("self", "a", "b=1"), attributes=("x",), value=1):
        return {
            "files": {
                "m.py": {
                    "functions": {},
                    "classes": {"C": {"bases": [], "methods": {"f": list(parameters)}, "attributes": list(attributes)}},
                    "variables": [],
                }
            },
            "values": {"m.E": {"A": value}},
        }

    def test_same(self):
        self.assertEqual(public_api.compare(self.api(), self.api()), ([], []))

    def test_optional_argument_can_be_added(self):
        for added in (["c=None"], ["*args"], ["*", "c=1"], ["**kwargs"]):
            with self.subTest(added=added):
                broken, unrecorded = public_api.compare(self.api(), self.api(["self", "a", "b=1"] + added))
                self.assertEqual(broken, [])
                self.assertEqual(len(unrecorded), 1)

    def test_changed_arguments_are_refused(self):
        changes = (
            ["self", "a"],  # 減った
            ["self", "b=1", "a"],  # 並びが変わった
            ["self", "a", "b=2"],  # 省略時の値が変わった
            ["self", "renamed", "b=1"],  # 名前が変わった
            ["self", "a", "b=1", "c"],  # 省略できない引数が増えた
            ["self", "a", "b=1", "*", "c"],
        )
        for parameters in changes:
            with self.subTest(parameters=parameters):
                broken, _ = public_api.compare(self.api(), self.api(parameters))
                self.assertEqual(len(broken), 1)

    def test_removed_names_are_refused(self):
        current = self.api(attributes=[])
        del current["files"]["m.py"]["classes"]["C"]["methods"]["f"]
        broken, unrecorded = public_api.compare(self.api(), current)
        self.assertEqual(len(broken), 2)
        self.assertEqual(unrecorded, [])

    def test_added_names_need_a_new_record(self):
        current = self.api(attributes=["x", "y"])
        current["files"]["m.py"]["classes"]["C"]["methods"]["g"] = ["self"]
        current["values"]["m.E"]["B"] = 2
        broken, unrecorded = public_api.compare(self.api(), current)
        self.assertEqual(broken, [])
        self.assertEqual(len(unrecorded), 3)

    def test_changed_values_are_refused(self):
        broken, _ = public_api.compare(self.api(), self.api(value=2))
        self.assertEqual(len(broken), 1)

    def test_record_format_can_be_read_back(self):
        import json

        text = public_api.dumps(self.api())
        self.assertEqual(json.loads(text), self.api())
        # 引数の一覧は、1行にまとまる
        self.assertIn('"f": ["self", "a", "b=1"]', text)


if __name__ == "__main__":
    unittest.main()
