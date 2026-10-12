#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/script_creator.py(新しいスクリプトのひな形を作る)のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import ast
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from CommandLoader import CommandLoader  # noqa: E402
from Commands.PythonCommandBase import ImageProcPythonCommand, PythonCommand  # noqa: E402
from services import script_creator, tag_editor  # noqa: E402
from services.script_creator import ScriptCreateError, ScriptSpec  # noqa: E402


def setUpModule():
    """通知のクラスを代役にする(コマンドを作るたびに、本物の通知先へ接続を確かめに行かないようにする)"""
    for name in ("Line_Notify", "Discord_Notify"):
        patcher = mock.patch(f"Commands.PythonCommandBase.{name}")
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)

class Folder(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.commands = os.path.join(self.base, "Commands", "PythonCommands")
        os.makedirs(os.path.join(self.commands, "bridge_functions"))
        with open(os.path.join(self.commands, "bridge_functions", "bridge_functions.py"), "w", encoding="utf-8") as file:
            file.write("class BridgeFunctions:\n    pass\n")
        os.makedirs(os.path.join(self.base, "Template", "Samples"))

    def create(self, **values):
        spec = ScriptSpec(**{"name": "テスト", "file_name": "my_script", **values})
        return script_creator.create_script(spec, self.base)

    def read(self, path: str) -> str:
        with open(path, encoding="utf-8", newline="") as file:
            return file.read()

    def error(self, **values) -> str:
        with self.assertRaises(ScriptCreateError) as raised:
            self.create(**values)
        return str(raised.exception)


class CheckTest(Folder):
    def test_name(self):
        self.assertEqual(script_creator.check_name("色違い厳選 (SV) ver.1"), "")
        self.assertIn("入力", script_creator.check_name(""))
        self.assertIn("改行", script_creator.check_name("a\nb"))
        self.assertIn("文字以内", script_creator.check_name("あ" * 101))

    def test_file_name(self):
        for name in ("a", "My-Script_01", "0start", "_x"):
            self.assertEqual(script_creator.check_file_name(name), "", name)
        for name, expected in (("", "入力"), ("日本語", "半角"), ("a b", "半角"), ("a.b", "半角"), ("x.py", ".py"), ("CON", "Windows"),
                               ("__init__", "__init__"), ("a" * 65, "文字以内"), ("a/b", "半角")):
            self.assertIn(expected, script_creator.check_file_name(name), name)

    def test_folder(self):
        for folder in ("", "MyScripts", "ゲーム/剣盾", "A-b_c"):
            self.assertEqual(script_creator.check_folder(folder, "格納場所"), "", folder)
        for folder in ("a.b", "..", "a:b", "x/..", "nul", 'a"b'):
            self.assertTrue(script_creator.check_folder(folder, "格納場所"), folder)
        self.assertEqual(script_creator.normalize_folder(" \\A\\ B //C/ "), "A/B/C")
        self.assertEqual(script_creator.normalize_folder("  "), "")

    def test_class_name(self):
        for file_name, expected in (("my_script", "MyScript"), ("shiny-hunt_01", "ShinyHunt01"), ("a", "A"), ("0start", "Command0start"),
                                    ("_", "Command"), ("ABC", "ABC"), ("raidBattle", "RaidBattle")):
            name = script_creator.class_name_for(file_name)
            self.assertEqual(name, expected)
            self.assertTrue(name.isidentifier())

    def test_errors(self):
        self.assertIn("スクリプト名", self.error(name="  "))
        self.assertIn("半角", self.error(file_name="だめ"))
        self.assertIn("格納場所", self.error(folder="a.b"))
        self.assertIn("画像保存先", self.error(template_folder="a*b"))
        self.assertIn("格納場所に使えません", self.error(folder="bridge_functions"))
        self.assertIn("格納場所に使えません", self.error(folder="__pycache__/x"))
        # 何も作っていない
        self.assertEqual(sorted(os.listdir(self.commands)), ["bridge_functions"])
        self.assertEqual(os.listdir(os.path.join(self.base, "Template")), ["Samples"])

    def test_existing_file_is_not_overwritten(self):
        result = self.create()
        before = self.read(result.path)
        self.assertIn("すでにあります", self.error(name="別の名前"))
        self.assertEqual(self.read(result.path), before)
        # 大文字・小文字だけが違う名前も、同じファイルになる環境では、作らない
        if os.path.exists(os.path.join(self.commands, "MY_SCRIPT.py")):
            self.assertIn("すでにあります", self.error(file_name="MY_SCRIPT"))

    def test_file_where_a_folder_is_needed(self):
        with open(os.path.join(self.commands, "taken"), "w") as file:
            file.write("")
        self.assertIn("同じ名前のファイル", self.error(folder="taken/sub"))
        with open(os.path.join(self.base, "Template", "image"), "w") as file:
            file.write("")
        self.assertIn("同じ名前のファイル", self.error(template_folder="image"))
        self.assertFalse(os.path.exists(os.path.join(self.commands, "my_script.py")))

    def test_bridge_is_required_when_it_is_used(self):
        shutil.rmtree(os.path.join(self.commands, "bridge_functions"))
        self.assertIn("BridgeFunctions", self.error(use_bridge=True))
        self.assertTrue(os.path.isfile(self.create(use_bridge=False).path))


class CreateTest(Folder):
    def scan(self, folder: str = ""):
        """作ったファイルを、コマンドの一覧と同じ方法で読み取る"""
        cwd = os.getcwd()
        os.chdir(self.base)
        try:
            return CommandLoader(os.path.join("Commands", "PythonCommands"), object).load()
        finally:
            os.chdir(cwd)

    def test_plain_script(self):
        result = self.create(name='A連打 "改"', file_name="mash-a")
        self.assertEqual(result.path, os.path.join(self.commands, "mash-a.py"))
        self.assertEqual((result.command_name, result.class_name, result.created_folders), ('A連打 "改" (mash-a)', "MashA", []))
        source = self.read(result.path)
        self.assertNotIn("\r", source)
        self.assertIn("from Commands.PythonCommandBase import PythonCommand\n", source)
        self.assertIn("class MashA(PythonCommand):\n", source)
        self.assertIn('    NAME = "A連打 \\"改\\""\n', source)
        self.assertIn("    def __init__(self):\n        super().__init__()\n", source)
        self.assertNotIn("TEMPLATE_DIR", source)
        self.assertNotIn("BridgeFunctions", source)
        ast.parse(source)
        entries = [entry for entry in self.scan() if entry.class_name == "MashA"]
        self.assertEqual([(entry.name, entry.tags) for entry in entries], [('A連打 "改" (mash-a)', [])])

    def test_image_script_creates_the_folders(self):
        result = self.create(folder="ゲーム\\剣盾", template_folder="SWSH/shiny")
        self.assertEqual(result.path, os.path.join(self.commands, "ゲーム", "剣盾", "my_script.py"))
        self.assertEqual(result.command_name, "テスト (ゲーム/剣盾/my_script)")
        self.assertEqual(result.created_folders, [
            os.path.join(self.commands, "ゲーム"), os.path.join(self.commands, "ゲーム", "剣盾"),
            os.path.join(self.base, "Template", "SWSH"), os.path.join(self.base, "Template", "SWSH", "shiny"),
        ])
        self.assertTrue(os.path.isdir(os.path.join(self.base, "Template", "SWSH", "shiny")))
        source = self.read(result.path)
        self.assertIn("from Commands.PythonCommandBase import ImageProcPythonCommand\n", source)
        self.assertIn('TEMPLATE_DIR = "SWSH/shiny"\n', source)
        self.assertIn("    def __init__(self, cam):\n        super().__init__(cam)\n", source)
        self.assertIn('# while not self.isContainTemplate(f"{TEMPLATE_DIR}/sample.png"):', source)
        entry = next(entry for entry in self.scan() if entry.class_name == "MyScript")
        self.assertEqual((entry.name, entry.tags), ("テスト (ゲーム/剣盾/my_script)", ["@ゲーム", "@剣盾"]))
        # 既にあるフォルダーは、作ったものに数えない
        second = self.create(file_name="second", folder="ゲーム/剣盾", template_folder="SWSH/shiny")
        self.assertEqual(second.created_folders, [])

    def test_bridge_script(self):
        result = self.create(use_bridge=True, template_folder="Samples")
        source = self.read(result.path)
        self.assertIn("from Commands.PythonCommands.bridge_functions.bridge_functions import BridgeFunctions\n", source)
        self.assertIn("class MyScript(ImageProcPythonCommand):\n", source)
        self.assertIn("        self.bf = BridgeFunctions(self)\n", source)
        # bridge_functions/Sample/bf_sample.py と同じ流れ: 用意 → プログラム情報の表示 → テンプレートのフォルダーの設定
        flow = ["self.bf = BridgeFunctions(self)", 'developer = "(名前)"', "self.bf.bf_show_informations(self.NAME, developer)",
                'self.bf.set_template_directory("./Template", TEMPLATE_DIR)', script_creator.WIDGET_BEGIN,
                "# ret = self.bf.bf_dialogue6widget_save_settings(", "# ret = self.bf.bf_dialogue6widget_select_settings(",
                script_creator.WIDGET_END, 'self.bf.bf_print("テスト を終了します")']
        positions = [source.index(text) for text in flow]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("# while not self.bf.bf_isContainTemplate(", source)
        ast.parse(source)
        # 画像の保存先がなくても、BridgeFunctions を使うなら、画像認識を使えるコマンドにする(BridgeFunctions の前提)
        source = self.read(self.create(file_name="no_image", use_bridge=True).path)
        self.assertIn("class NoImage(ImageProcPythonCommand):\n", source)
        self.assertNotIn("TEMPLATE_DIR", source)
        self.assertNotIn("set_template_directory", source)

    def uncommented(self, source: str) -> str:
        """ウィジェットの例の「# 」を外したソース"""
        lines, inside = [], False
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped == script_creator.WIDGET_BEGIN:
                inside = True
            elif stripped == script_creator.WIDGET_END:
                inside = False
            elif inside:
                indent = line[: len(line) - len(line.lstrip())]
                self.assertTrue(stripped.startswith("#"), line)
                line = indent + stripped[2:] if stripped.startswith("# ") else indent + stripped[1:]
            lines.append(line)
        self.assertFalse(inside)
        return "\n".join(lines)

    def test_widget_example_is_commented_out_in_every_form(self):
        for values in ({}, {"template_folder": "img"}, {"use_bridge": True}, {"use_bridge": True, "template_folder": "img"}):
            source = script_creator.build_source(ScriptSpec("n", "my_file", **values))
            begin, end = source.index(script_creator.WIDGET_BEGIN), source.index(script_creator.WIDGET_END)
            block = source[begin:end].split("\n")[1:-1]
            self.assertGreater(len(block), 15)
            # ウィジェットに関わる行は、すべてコメント(そのまま実行しても、ダイアログは開かない)
            self.assertTrue(all(line.strip().startswith("#") for line in block), values)
            self.assertNotIn("dialogue", "\n".join(line for line in source.split("\n") if not line.strip().startswith("#")))
            if values.get("use_bridge"):
                self.assertIn("# ret = self.bf.bf_dialogue6widget_save_settings(", source)
                self.assertIn("# ret = self.bf.bf_dialogue6widget_select_settings(", source)
            else:
                # 使わない場合は、self.dialogue6widget と print だけ(設定の保存や、os は使わない)
                self.assertEqual(source.count("# ret = self.dialogue6widget("), 2)
                for text in ("save_settings", "select_settings", "print_tb", "settings_file", "settings_dir", "import os", "self.bf"):
                    self.assertNotIn(text, source, text)
                calls = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
                         for node in ast.walk(ast.parse(self.uncommented(source)).body[-1].body[-1]) if isinstance(node, ast.Call)}
                self.assertEqual(calls, {"dialogue6widget", "print", "wait"})
            # 「# 」を外しても、文法の誤りがない
            ast.parse(self.uncommented(source))

    def test_widget_example_runs_when_uncommented(self):
        # BridgeFunctions を使わないもの: 「# 」を外して実行すると、ダイアログを 2 回呼んで、結果を print する
        path = self.create(file_name="widget").path
        namespace = {"__name__": "created_widget", "__file__": path}
        exec(compile(self.uncommented(self.read(path)), path, "exec"), namespace)
        cls = namespace["Widget"]
        self.assertTrue(callable(PythonCommand.dialogue6widget))
        command = cls()
        with mock.patch.object(cls, "dialogue6widget", side_effect=[["one"], ["two"]]) as dialogue, \
                mock.patch.object(cls, "wait"), mock.patch("builtins.print") as printed:
            command.do()
        self.assertEqual(dialogue.call_args_list, [
            mock.call("config", [["Entry", "テスト1", 1]], desc="テスト用ウィジェット"),
            mock.call("config", [["Combo", "テスト2", ["A", "B", "C"], "A"]], desc="テスト用ウィジェット2"),
        ])
        self.assertEqual([call.args[0] for call in printed.call_args_list],
                         ["テスト を開始します", "ウィジェット1結果:one", "ウィジェット2結果:two", "テスト を終了します"])

    def test_bridge_functions_used_by_the_template_exist(self):
        # ひな形が呼ぶ橋渡し関数が、同梱の bridge_functions にあること
        from Commands.PythonCommands.bridge_functions.bridge_functions import BridgeFunctions

        source = self.uncommented(script_creator.build_source(ScriptSpec("n", "f", use_bridge=True, template_folder="t")))
        names = {node.attr for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute)
                 and isinstance(node.value, ast.Attribute) and node.value.attr == "bf"}
        self.assertEqual(names, {"bf_show_informations", "set_template_directory", "bf_dialogue6widget_save_settings",
                                 "bf_dialogue6widget_select_settings", "bf_print", "bf_print_w"})
        for name in names | {"bf_isContainTemplate"}:
            self.assertTrue(callable(getattr(BridgeFunctions, name)), name)

    def test_created_scripts_can_be_imported_and_run(self):
        # 実際の Commands の基底クラスで、読み込んで実行できる(BridgeFunctions を使わないもの)
        for index, values in enumerate(({}, {"template_folder": "img"})):
            path = self.create(file_name=f"run{index}", **values).path
            namespace = {"__name__": f"created{index}"}
            exec(compile(self.read(path), path, "exec"), namespace)
            cls = namespace[f"Run{index}"]
            self.assertTrue(issubclass(cls, ImageProcPythonCommand if values else PythonCommand))
            self.assertEqual((cls.NAME, cls.TAGS), ("テスト", []))

    def test_tags_of_a_created_script_can_be_edited(self):
        result = self.create()
        source = tag_editor.read_source(result.path, result.class_name)
        self.assertEqual((source.editable, source.tags), (True, []))
        tag_editor.save_tags(result.path, source.digest, {result.class_name: ["新規"]})
        self.assertIn('    TAGS = ["新規"]\n', self.read(result.path))

    def test_folder_lists(self):
        os.makedirs(os.path.join(self.commands, "B", "inner"))
        os.makedirs(os.path.join(self.commands, "a"))
        os.makedirs(os.path.join(self.commands, "__pycache__"))
        os.makedirs(os.path.join(self.commands, ".hidden"))
        self.assertEqual(script_creator.script_folders(self.base), ["a", "B", "B/inner"])
        self.assertEqual(script_creator.template_folders(self.base), ["Samples"])
        self.assertEqual(script_creator.list_folders(os.path.join(self.base, "none")), [])
        self.assertTrue(script_creator.bridge_available(self.base))

    def test_generated_source_passes_the_lint(self):
        # 作ったファイルに、使っていない import の指摘が出ないこと(noqa を付けている)
        source = script_creator.build_source(ScriptSpec("n", "f", use_bridge=True, template_folder="t"))
        tree = ast.parse(source)
        imported = {alias.asname or alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
        used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertEqual(imported - used, {"Button", "Direction", "Hat"})
        self.assertIn("import os  # noqa: F401", source)
        self.assertIn("from Commands.Keys import Button, Direction, Hat  # noqa: F401", source)


class TemplateLocationTest(Folder):
    """画像の保存先を、スクリプトの格納場所の中にする(BridgeFunctions を使う場合だけ)"""

    def test_images_in_the_script_folder(self):
        result = self.create(folder="Pack", use_bridge=True, template_folder="images", template_location=script_creator.IN_SCRIPT_FOLDER)
        images = os.path.join(self.commands, "Pack", "images")
        self.assertTrue(os.path.isdir(images))
        self.assertFalse(os.path.exists(os.path.join(self.base, "Template", "images")))
        self.assertEqual(result.created_folders, [os.path.join(self.commands, "Pack"), images])
        source = self.read(result.path)
        self.assertIn("# テンプレート画像を置くフォルダー(このファイルと同じフォルダーの中)\nTEMPLATE_DIR = \"images\"\n", source)
        # bridge_functions/Sample/bf_sample.py と同じ書き方
        self.assertIn("        self.bf.set_template_directory(os.path.join(os.path.dirname(__file__)), TEMPLATE_DIR)\n", source)
        self.assertNotIn('"./Template"', source)
        # os を実際に使うので、指摘を止める印は付けない
        self.assertIn("\nimport os\n", source)
        ast.parse(source)

    def test_images_in_template_is_the_default(self):
        result = self.create(use_bridge=True, template_folder="images")
        self.assertTrue(os.path.isdir(os.path.join(self.base, "Template", "images")))
        self.assertIn('        self.bf.set_template_directory("./Template", TEMPLATE_DIR)\n', self.read(result.path))

    def test_script_folder_location_needs_bridge_functions(self):
        message = self.error(template_folder="images", template_location=script_creator.IN_SCRIPT_FOLDER)
        self.assertIn("BridgeFunctions を使用する場合だけ", message)
        self.assertEqual(sorted(os.listdir(self.commands)), ["bridge_functions"])
        self.assertIn("種類", self.error(template_location="elsewhere"))
        # 画像を使わないなら、種類は関係ない
        self.assertTrue(os.path.isfile(self.create(template_location=script_creator.IN_SCRIPT_FOLDER).path))

    def test_set_template_directory_points_at_the_created_folder(self):
        # 作ったスクリプトの set_template_directory の引数が、実際に作ったフォルダーを指していること
        result = self.create(folder="Pack", use_bridge=True, template_folder="img/sub", template_location=script_creator.IN_SCRIPT_FOLDER)
        calls = []

        class FakeBridge:
            def __init__(self, command):
                pass

            def set_template_directory(self, name1, name2):
                calls.append(os.path.isdir(os.path.join(name1, name2)))

            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        source = self.read(result.path).replace(script_creator.BRIDGE_IMPORT, "")
        namespace = {"__name__": "created_pack", "__file__": result.path, "BridgeFunctions": FakeBridge}
        exec(compile(source, result.path, "exec"), namespace)
        command = namespace["MyScript"](None)
        with mock.patch.object(namespace["MyScript"], "wait"):
            command.do()
        self.assertEqual(calls, [True])


class ReadmeAndLicenseTest(Folder):
    """格納場所に一緒に作る、README.md と License.txt"""

    def test_files_are_created_next_to_the_script(self):
        result = self.create(name="色違い厳選", folder="Pack", template_folder="img")
        folder = os.path.join(self.commands, "Pack")
        self.assertEqual(result.created_files, [os.path.join(folder, "README.md"), os.path.join(folder, "License.txt")])
        self.assertEqual(result.skipped_files, [])
        readme = self.read(os.path.join(folder, "README.md"))
        # bridge_functions/README.md と同じ章立て
        positions = [readme.index(text) for text in ("fileencoding=utf-8", "色違い厳選 ver.0.0.1 作成者：(名前)", "■要約", "■開発環境",
                                                     "■事前準備", "■使用方法", "■対象のバージョン", "■利用上の注意", "■その他")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("SerialController\\Commands\\PythonCommands\\Pack\\my_script.pyとなる想定です。", readme)
        self.assertIn("テンプレート画像は、SerialController\\Template\\imgにおいてください。", readme)
        self.assertIn("「色違い厳選 (Pack/my_script)」を選び", readme)
        self.assertIn("商用利用/自作発言はお控えください。", readme)
        self.assertNotIn("橋渡し関数", readme)
        self.assertNotIn("\r", readme)

    def test_license_forbids_commercial_use_and_is_not_mit(self):
        result = self.create(name="色違い厳選", folder="Pack")
        text = self.read(result.created_files[1])
        self.assertTrue(text.startswith(f"色違い厳選\nCopyright (C) {__import__('datetime').date.today().year}年 (名前)\n"))
        self.assertIn("・商用利用(※)をしない。", text)
        self.assertIn("個人のみ使用可能", text)
        self.assertNotIn("MIT", text)
        self.assertNotIn("Permission is hereby granted", text)
        # 条項は、手本(bridge_functions/License.txt)と同じ 6 つ
        self.assertEqual([line[:2] for line in text.split("\n") if line[:2] in ("1.", "2.", "3.", "4.", "5.", "6.")],
                         ["1.", "2.", "3.", "4.", "5.", "6."])
        reference = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Commands", "PythonCommands",
                                 "bridge_functions", "License.txt")
        with open(reference, encoding="utf-8") as file:
            original = file.read().replace("\r\n", "\n")
        for number in ("1.", "2.", "3.", "4.", "6."):
            clause = next(line for line in original.split("\n") if line.startswith(number))
            self.assertIn(clause, text, number)

    def test_bridge_script_mentions_the_bridge_functions(self):
        result = self.create(folder="Pack", use_bridge=True, template_folder="img", template_location=script_creator.IN_SCRIPT_FOLDER)
        readme = self.read(result.created_files[0])
        self.assertIn("橋渡し関数(bridge_functions)が必要です。", readme)
        self.assertIn("テンプレート画像は、SerialController\\Commands\\PythonCommands\\Pack\\imgにおいてください。", readme)
        self.assertIn("※Poke-Controller Modifiedでは、SerialController\\Template\\imgにおいてください", readme)
        self.assertIn("■使用しているプログラム\n* 本プログラムは、Poke-Controller Modified/Extension 橋渡し関数(作成者：フウ(@dragonite303))を使用しています。", readme)
        self.assertIn("Poke-Controller Modified/Extension 橋渡し関数", self.read(result.created_files[1]))

    def test_existing_files_are_kept(self):
        first = self.create(name="一つ目", folder="Pack")
        readme, license_text = (self.read(path) for path in first.created_files)
        second = self.create(name="二つ目", file_name="second", folder="Pack")
        self.assertEqual((second.created_files, second.skipped_files), ([], first.created_files))
        self.assertEqual([self.read(path) for path in first.created_files], [readme, license_text])
        self.assertIn("一つ目", readme)
        # 片方だけある場合は、ない方だけ作る
        os.remove(first.created_files[1])
        third = self.create(name="三つ目", file_name="third", folder="Pack")
        self.assertEqual((third.created_files, third.skipped_files), ([first.created_files[1]], [first.created_files[0]]))
        self.assertTrue(self.read(first.created_files[1]).startswith("三つ目\n"))

    def test_files_in_the_root_folder(self):
        result = self.create()
        self.assertEqual(result.created_files, [os.path.join(self.commands, "README.md"), os.path.join(self.commands, "License.txt")])
        self.assertIn("* SerialController\\Commands\\PythonCommands\\my_script.pyとなるようにおいてください。", self.read(result.created_files[0]))

    def test_author_is_written_to_every_file(self):
        result = self.create(name="色違い厳選", author='  フウ "@x"  ', folder="Pack", use_bridge=True)
        self.assertIn('        developer = "フウ \\"@x\\""\n', self.read(result.path))
        self.assertIn('色違い厳選 ver.0.0.1 作成者：フウ "@x"\n', self.read(result.created_files[0]))
        self.assertIn('年 フウ "@x"\n', self.read(result.created_files[1]))
        for path in [result.path] + result.created_files:
            self.assertNotIn("(名前)", self.read(path), path)
        ast.parse(self.read(result.path))

    def test_author_can_be_left_empty(self):
        result = self.create(folder="Pack", use_bridge=True, author="   ")
        self.assertIn('        developer = "(名前)"\n', self.read(result.path))
        self.assertIn("作成者：(名前)\n", self.read(result.created_files[0]))
        self.assertIn("年 (名前)\n", self.read(result.created_files[1]))

    def test_author_is_checked(self):
        self.assertEqual(script_creator.check_author(""), "")
        self.assertEqual(script_creator.check_author("フウ(@dragonite303)"), "")
        self.assertIn("改行", self.error(author="a\nb"))
        self.assertIn("文字以内", self.error(author="あ" * 101))
        self.assertEqual(sorted(os.listdir(self.commands)), ["bridge_functions"])

    def test_author_is_remembered(self):
        self.assertEqual(script_creator.load_author(self.base), "")
        script_creator.save_author("  フウ(@x) ", self.base)
        self.assertEqual(script_creator.load_author(self.base), "フウ(@x)")
        self.assertTrue(os.path.isfile(os.path.join(self.base, "profiles", "script_creator.json")))
        # 空にして作ったときは、空を覚える
        script_creator.save_author("", self.base)
        self.assertEqual(script_creator.load_author(self.base), "")
        # 壊れたファイルや、使えない値は、空として扱う
        path = os.path.join(self.base, "profiles", "script_creator.json")
        for content in ("not json", "[1, 2]", '{"author": 5}', '{"author": "a\\nb"}'):
            with open(path, "w", encoding="utf-8") as file:
                file.write(content)
            self.assertEqual(script_creator.load_author(self.base), "", content)

    def test_app_version_is_written(self):
        spec = ScriptSpec("n", "f").normalized()
        self.assertIn("Poke-Controller Modified Extension ver.1.2.3", script_creator.build_readme(spec, "1.2.3"))
        self.assertIn("　Poke-Controller Modified Extension\n", script_creator.build_readme(spec))
        self.assertIn("Copyright (C) 2030年", script_creator.build_license(spec, 2030))


if __name__ == "__main__":
    unittest.main()
