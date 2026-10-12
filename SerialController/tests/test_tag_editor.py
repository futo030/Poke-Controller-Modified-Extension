#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/tag_editor.py(コマンドのタグの読み取りと書き換え)のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from CommandLoader import CommandEntry, CommandLoader  # noqa: E402
from services import tag_editor  # noqa: E402
from services.tag_editor import CHANGED, LOCKED, NOT_EDITABLE, TagEditError  # noqa: E402

SIMPLE = '''from Commands.PythonCommandBase import PythonCommand


class Mash(PythonCommand):
    NAME = "A連打"
    TAGS = ["連打", "基本"]  # コメント

    def do(self):
        pass


class NoTags(PythonCommand):
    """説明"""

    NAME = "タグなし"

    def do(self):
        pass
'''


class Folder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)

    def write(self, text: str, name: str = "command.py", newline: str = "\n") -> str:
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(text.replace("\n", newline))
        return path

    def read(self, path: str) -> str:
        with open(path, encoding="utf-8", newline="") as file:
            return file.read()

    def save(self, path: str, changes: dict) -> str:
        """読み取ってすぐ保存する(戻り値: 保存した後のファイルの内容)"""
        digest = tag_editor.read_source(path, next(iter(changes))).digest
        tag_editor.save_tags(path, digest, changes)
        return self.read(path)


class ReadTest(Folder):
    def test_reads_the_tags_written_in_the_class(self):
        path = self.write(SIMPLE)
        source = tag_editor.read_source(path, "Mash")
        self.assertEqual((source.tags, source.editable, source.reason), (["連打", "基本"], True, ""))
        source = tag_editor.read_source(path, "NoTags")
        self.assertEqual((source.tags, source.editable), ([], True))
        self.assertTrue(source.digest)

    def test_other_literal_forms_are_editable(self):
        for value, tags in (('("a", "b")', ["a", "b"]), ('"a", "b"', ["a", "b"]), ('"only"', ["only"]), ("[]", []),
                            ('[\n        "a",\n        "b",\n    ]', ["a", "b"])):
            path = self.write(f"class C(Base):\n    NAME = 'n'\n    TAGS = {value}\n")
            source = tag_editor.read_source(path, "C")
            self.assertEqual((source.tags, source.editable), (tags, True), value)

    def test_annotated_assignment_is_editable(self):
        path = self.write("class C(Base):\n    NAME = 'n'\n    TAGS: list = ['a']\n")
        self.assertEqual(tag_editor.read_source(path, "C").tags, ["a"])
        self.assertIn("    TAGS: list = [\"a\", \"b\"]\n", self.save(path, {"C": ["a", "b"]}))

    def test_forms_that_are_not_a_plain_list_are_not_editable(self):
        cases = {
            "TAGS = BASE + ['x']": "一覧ではない",
            "TAGS = [GAME, 'x']": "一覧ではない",
            "TAGS = make_tags()": "一覧ではない",
            "TAGS = ['a', 1]": "一覧ではない",
            "TAGS = OTHER = ['a']": "ほかの変数と一緒",
            "TAGS = ['a']\n    TAGS = ['b']": "2 か所以上",
            "TAGS: list": "一覧ではない",
        }
        for body, expected in cases.items():
            path = self.write(f"BASE = ['b']\nGAME = 'g'\n\n\nclass C(Base):\n    NAME = 'n'\n    {body}\n")
            source = tag_editor.read_source(path, "C")
            self.assertFalse(source.editable, body)
            self.assertIn(expected, source.reason, body)
            self.assertEqual(source.tags, [])
            before = self.read(path)
            with self.assertRaises(TagEditError) as raised:
                tag_editor.save_tags(path, source.digest, {"C": ["new"]})
            self.assertEqual(raised.exception.kind, NOT_EDITABLE)
            self.assertEqual(self.read(path), before)

    def test_unreadable_sources_are_not_editable(self):
        broken = self.write("class C(Base:\n    NAME = 'n'\n", "broken.py")
        self.assertIn("文法の誤り", tag_editor.read_source(broken, "C").reason)
        self.assertIn("ありません", tag_editor.read_source(self.write(SIMPLE), "Missing").reason)
        self.assertIn("読めません", tag_editor.read_source(os.path.join(self.folder, "none.py"), "C").reason)
        cp932 = os.path.join(self.folder, "cp932.py")
        with open(cp932, "wb") as file:
            file.write("class C(Base):\n    NAME = 'あ'\n".encode("cp932"))
        self.assertIn("UTF-8", tag_editor.read_source(cp932, "C").reason)
        one_line = self.write("class C(Base): NAME = 'n'\n", "one_line.py")
        self.assertFalse(tag_editor.read_source(one_line, "C").editable)
        # ファイルに書かれていないコマンド(.py 以外)
        other = tag_editor.read_source(os.path.join(self.folder, "package.bin"), "C")
        self.assertEqual((other.editable, other.digest), (False, ""))


class SaveTest(Folder):
    def test_only_the_value_is_replaced(self):
        path = self.write(SIMPLE)
        text = self.save(path, {"Mash": ["連打", "剣盾", 'a"b']})
        self.assertEqual(text, SIMPLE.replace('["連打", "基本"]', '["連打", "剣盾", "a\\"b"]'))
        self.assertEqual(tag_editor.read_source(path, "Mash").tags, ["連打", "剣盾", 'a"b'])

    def test_line_is_added_below_name_when_the_class_has_no_tags(self):
        path = self.write(SIMPLE)
        text = self.save(path, {"NoTags": ["新規"]})
        self.assertEqual(text, SIMPLE.replace('    NAME = "タグなし"\n', '    NAME = "タグなし"\n    TAGS = ["新規"]\n'))

    def test_line_is_added_when_the_class_has_no_name(self):
        # NAME を基底クラスから引き継いでいるクラス: 説明の下、説明もなければ中身の先頭
        path = self.write('class A(Base):\n    """説明"""\n\n    def do(self):\n        pass\n')
        self.assertEqual(self.save(path, {"A": ["x"]}),
                         'class A(Base):\n    """説明"""\n    TAGS = ["x"]\n\n    def do(self):\n        pass\n')
        path = self.write("class A(Base):\n\tdef do(self):\n\t\tpass\n")
        self.assertEqual(self.save(path, {"A": ["x"]}), 'class A(Base):\n\tTAGS = ["x"]\n\tdef do(self):\n\t\tpass\n')

    def test_empty_tags(self):
        path = self.write(SIMPLE)
        # TAGS のないクラスを空にしても、何も足さない
        self.assertEqual(self.save(path, {"NoTags": []}), SIMPLE)
        self.assertIn("    TAGS = []  # コメント\n", self.save(path, {"Mash": []}))

    def test_several_classes_of_one_file_are_saved_at_once(self):
        path = self.write(SIMPLE)
        text = self.save(path, {"Mash": ["m"], "NoTags": ["n1", "n2"]})
        self.assertIn('    TAGS = ["m"]  # コメント\n', text)
        self.assertIn('    NAME = "タグなし"\n    TAGS = ["n1", "n2"]\n', text)
        self.assertEqual(tag_editor.read_source(path, "NoTags").tags, ["n1", "n2"])

    def test_multi_line_and_parenthesized_values(self):
        path = self.write('class C(Base):\n    NAME = "n"\n    TAGS = [\n        "a",  # 1\n        "b",\n    ]\n    X = 1\n')
        self.assertEqual(self.save(path, {"C": ["z"]}), 'class C(Base):\n    NAME = "n"\n    TAGS = ["z"]\n    X = 1\n')
        path = self.write('class C(Base):\n    NAME = "n"\n    TAGS = ("a")\n')
        self.assertEqual(self.save(path, {"C": ["a", "b"]}), 'class C(Base):\n    NAME = "n"\n    TAGS = ["a", "b"]\n')
        path = self.write('class C(Base):\n    NAME = "n"\n    TAGS = "a", "b"\n')
        self.assertEqual(self.save(path, {"C": ["c"]}), 'class C(Base):\n    NAME = "n"\n    TAGS = ["c"]\n')

    def test_position_with_wide_characters_before_the_value(self):
        path = self.write('class C(Base):\n    NAME = "名前"; TAGS = ["あ", "い"]; X = "後ろ"\n')
        self.assertEqual(self.save(path, {"C": ["う"]}), 'class C(Base):\n    NAME = "名前"; TAGS = ["う"]; X = "後ろ"\n')

    def test_newlines_are_kept(self):
        for newline in ("\r\n", "\r"):
            path = self.write(SIMPLE, newline=newline)
            text = self.save(path, {"Mash": ["x"], "NoTags": ["y"]})
            expected = SIMPLE.replace('["連打", "基本"]', '["x"]').replace(
                '    NAME = "タグなし"\n', '    NAME = "タグなし"\n    TAGS = ["y"]\n')
            self.assertEqual(text, expected.replace("\n", newline))

    def test_file_changed_after_reading_is_not_overwritten(self):
        path = self.write(SIMPLE)
        digest = tag_editor.read_source(path, "Mash").digest
        changed = SIMPLE.replace("pass", "print('edited')", 1)
        self.write(changed)
        with self.assertRaises(TagEditError) as raised:
            tag_editor.save_tags(path, digest, {"Mash": ["x"]})
        self.assertEqual(raised.exception.kind, CHANGED)
        self.assertEqual(self.read(path), changed)

    def test_saving_twice_needs_the_new_digest(self):
        path = self.write(SIMPLE)
        digest = tag_editor.read_source(path, "Mash").digest
        new_digest = tag_editor.save_tags(path, digest, {"Mash": ["x"]})
        self.assertNotEqual(new_digest, digest)
        with self.assertRaises(TagEditError):
            tag_editor.save_tags(path, digest, {"Mash": ["y"]})
        self.assertEqual(tag_editor.save_tags(path, new_digest, {"Mash": ["y"]}), tag_editor.read_source(path, "Mash").digest)
        # 同じ内容なら、書き込まない(印も変わらない)
        self.assertEqual(tag_editor.save_tags(path, tag_editor.read_source(path, "Mash").digest, {"Mash": ["y"]}),
                         tag_editor.read_source(path, "Mash").digest)

    def test_read_only_file_reports_that_it_cannot_be_written(self):
        path = self.write(SIMPLE)
        digest = tag_editor.read_source(path, "Mash").digest
        os.chmod(path, stat.S_IREAD)
        self.addCleanup(os.chmod, path, stat.S_IWRITE | stat.S_IREAD)
        with self.assertRaises(TagEditError) as raised:
            tag_editor.save_tags(path, digest, {"Mash": ["x"]})
        self.assertEqual(raised.exception.kind, LOCKED)
        self.assertEqual(self.read(path), SIMPLE)

    @unittest.skipUnless(os.name == "nt", "Windows での、ほかのアプリが開いているファイル")
    def test_file_opened_exclusively_by_another_program(self):
        import msvcrt

        path = self.write(SIMPLE)
        digest = tag_editor.read_source(path, "Mash").digest
        with open(path, "r+b") as other:
            msvcrt.locking(other.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                with self.assertRaises(TagEditError) as raised:
                    tag_editor.save_tags(path, digest, {"Mash": ["x"]})
            finally:
                other.seek(0)
                msvcrt.locking(other.fileno(), msvcrt.LK_UNLCK, 1)
        self.assertEqual(raised.exception.kind, LOCKED)
        self.assertEqual(self.read(path), SIMPLE)


class EntryTest(Folder):
    def test_saved_tags_are_what_the_command_list_reads(self):
        root = os.path.join(self.folder, "Commands", "PythonCommands", "Games")
        os.makedirs(root)
        with open(os.path.join(root, "sample.py"), "w", encoding="utf-8") as file:
            file.write(SIMPLE)
        cwd = os.getcwd()
        os.chdir(self.folder)
        self.addCleanup(os.chdir, cwd)
        loader = CommandLoader(os.path.join("Commands", "PythonCommands"), object)
        entries = {entry.class_name: entry for entry in loader.load()}
        self.assertEqual(tag_editor.split_entry_tags(entries["Mash"]), (["連打", "基本"], ["@Games"]))
        self.assertEqual(tag_editor.split_entry_tags(entries["NoTags"]), ([], ["@Games"]))
        source = tag_editor.read_source(entries["Mash"].file_path, "Mash")
        tag_editor.save_tags(source.file_path, source.digest, {"Mash": ["剣盾"], "NoTags": ["新規"]})
        entries = {entry.class_name: entry for entry in loader.reload()}
        self.assertEqual(entries["Mash"].tags, ["剣盾", "@Games"])
        self.assertEqual(entries["NoTags"].tags, ["新規", "@Games"])

    def test_entries_without_a_module_have_no_folder_tags(self):
        entry = CommandEntry(name="x", tags=["@other"], module_name="", class_name="x", file_path="x.bin")
        self.assertEqual(tag_editor.split_entry_tags(entry), (["@other"], []))

    def test_check_tag(self):
        self.assertEqual(tag_editor.check_tag("  剣盾 ", ["連打"]), ("剣盾", ""))
        for text, expected in (("", "入力"), ("   ", "入力"), ("@Games", "フォルダー"), ("連打", "すでに"), ("a\tb", "改行")):
            self.assertIn(expected, tag_editor.check_tag(text, ["連打"])[1], text)

    def test_format_tags(self):
        self.assertEqual(tag_editor.format_tags([]), "[]")
        self.assertEqual(tag_editor.format_tags(["a", "い", "\\"]), '["a", "い", "\\\\"]')


class BulkEditTest(unittest.TestCase):
    """タグの一括変更(名前の変更・削除)に使う関数"""

    def test_rename_keeps_the_position(self):
        self.assertEqual(tag_editor.replace_tag(["a", "b", "c"], "b", "x"), ["a", "x", "c"])

    def test_rename_to_an_existing_tag_merges_them(self):
        self.assertEqual(tag_editor.replace_tag(["a", "b", "c"], "a", "c"), ["b", "c"])

    def test_delete(self):
        self.assertEqual(tag_editor.replace_tag(["a", "b", "c"], "b"), ["a", "c"])

    def test_missing_tag_changes_nothing_and_the_list_is_copied(self):
        tags = ["a", "b"]
        result = tag_editor.replace_tag(tags, "x", "y")
        self.assertEqual(result, tags)
        self.assertIsNot(result, tags)

    def test_new_name_is_checked(self):
        self.assertEqual(tag_editor.check_new_name("a", " b "), ("b", ""))
        for text in ("", "   ", "a", " a ", "@folder", "x\ny", "x\ty"):
            with self.subTest(text=text):
                self.assertNotEqual(tag_editor.check_new_name("a", text)[1], "")
        self.assertIn("入力", tag_editor.check_new_name("a", "  ")[1])
        self.assertIn("同じ", tag_editor.check_new_name("a", "a")[1])


if __name__ == "__main__":
    unittest.main()
